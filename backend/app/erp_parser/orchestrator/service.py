"""Universal ERP parser orchestrator. Existing extractors stay in place."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

from app.core.logging import get_logger
from app.erp_parser.confidence import compute_erp_confidence
from app.erp_parser.llm_header_resolver import (
    LLMHeaderResolver,
    LLMHeaderResolverError,
)
from app.erp_parser.orchestrator.candidates import (
    PARSER_LABEL,
    run_monthly_sheets,
    run_sheet_candidates,
)
from app.erp_parser.orchestrator.classifier import classify_workbook, fingerprint_matched
from app.erp_parser.orchestrator.detector import fingerprint_sheet
from app.erp_parser.orchestrator.confidence_engine import decision_band, score_extraction
from app.erp_parser.orchestrator.deadline import HUMAN_REVIEW_TIMEOUT, StageTimeout, run_bounded
from app.erp_parser.orchestrator.fingerprint import build_fingerprint
from app.erp_parser.orchestrator.structure import extract_with_layout
from app.erp_parser.orchestrator.types import ParserResult
from app.erp_parser.orchestrator.versions import parser_version
from app.erp_parser.workbook_lifecycle import open_workbook_once
from app.exceptions import ExcelProcessingError

logger = get_logger(__name__)

_COULD_NOT_MAP = (
    "Could not map Customer, Product, and Sales Quantity columns. "
    "Please verify the ERP export has recognizable headers."
)

SEMANTIC_PROMPT = """You are an ERP document structure analyzer.

You will receive sheet metadata, header cells, optional title/metadata rows above the table, and at most 5 sample data rows.
Do not invent values. Do not invent column names that are absent from the headers.
Do not extract customer/product/quantity cell values — only identify which columns (and optional title) map to them.

Return JSON only:
{
  "layout_type": "standard_header",
  "customer_column": "",
  "product_column": "",
  "quantity_column": "",
  "product_header_row": null,
  "month_header_row": null,
  "ignore_columns": [],
  "grouping": "",
  "parser_hint": "header",
  "confidence": 0,
  "is_sales_table": true,
  "product_from_title": ""
}

customer_column, product_column, and quantity_column must be exact header strings from the provided headers (or null).
layout_type must be one of: standard_header, matrix_month, cross_product_matrix, stock_item_register, metadata, product_blocks, unknown.
parser_hint must be one of: header, matrix_month, cross_product_matrix, stock_item_register, metadata, product_blocks.
When both inbound and outbound quantity columns exist (e.g. Qty. In and Qty. Out), quantity_column must be the outbound/sales quantity — never Qty. In.
If a title above the table names the product and there is no product column, set product_from_title to that exact title text.
Confidence 0-100. Use null when uncertain.
"""


def _sheet_has_usable_data(sheet: Dict[str, Any]) -> bool:
    """True when a worksheet has enough non-empty structure to try LLM assist."""
    matrix = sheet.get("matrix") or []
    if not matrix:
        return False
    non_empty = sum(1 for row in matrix if any(cell not in (None, "") for cell in row))
    if non_empty < 2:
        return False
    from app.erp_parser.sheet_detector import score_sheet

    return score_sheet(matrix) >= 10 or non_empty >= 3


def _mapping_incomplete(result: Optional[ParserResult]) -> bool:
    """True when Customer / Product / Quantity cannot be trusted from the deterministic result."""
    if result is None:
        return True
    if result.rows:
        from app.erp_parser.orchestrator.confidence_engine import _qty_ok

        total = len(result.rows)
        missing_c = sum(1 for row in result.rows if not str(row.get("customer_name") or "").strip())
        missing_p = sum(1 for row in result.rows if not str(row.get("product") or "").strip())
        missing_q = sum(1 for row in result.rows if not _qty_ok(row))
        if missing_c > total * 0.25 or missing_p > total * 0.25 or missing_q > total * 0.25:
            return True
        return False
    from app.erp_parser.parser_service import _mapping_complete

    positions = (result.mapped or {}).get("positions") or {}
    qty_cols = (result.mapped or {}).get("quantity_columns") or []
    return not _mapping_complete(positions, qty_cols)


def _needs_llm_fallback(
    winner: Optional[ParserResult],
    sheets: Sequence[Dict[str, Any]],
    classification: Any,
) -> tuple[bool, str]:
    """
    Decide whether Bedrock structure assist must run.

    Accuracy 0 / missing mapping / low confidence with usable sheet data → True.
    High-confidence complete deterministic results → False.
    """
    usable = [item for item in sheets if _sheet_has_usable_data(item)]
    if not usable:
        return False, ""

    if winner is None:
        return True, "no_valid_layout"
    if not winner.rows:
        return True, "zero_rows"

    conf = float(winner.confidence or 0)
    from app.erp_parser.parser_service import LLM_FALLBACK_THRESHOLD

    # Existing threshold (85): complete deterministic results at/above it skip LLM.
    # Accuracy 0 / low scores with usable sheet data always get a Bedrock chance.
    if conf < LLM_FALLBACK_THRESHOLD:
        if conf <= 0:
            return True, "zero_accuracy"
        if conf < 70:
            return True, "low_accuracy"
        return True, "low_confidence"

    if _mapping_incomplete(winner):
        return True, "incomplete_mapping"

    positions = (winner.mapped or {}).get("positions") or {}
    qty_cols = (winner.mapped or {}).get("quantity_columns") or []
    field_conf = (winner.mapped or {}).get("confidences") or {}
    if winner.parser_name == "header":
        if positions.get("customer") is None:
            return True, "missing_customer"
        if positions.get("product") is None:
            return True, "missing_product"
        if positions.get("quantity") is None and not qty_cols:
            return True, "missing_quantity"
        for field, reason in (
            ("customer", "missing_customer"),
            ("product", "missing_product"),
            ("quantity", "missing_quantity"),
        ):
            if float(field_conf.get(field) or 100) < 70:
                return True, reason

    # Multi-sheet: usable data elsewhere but no strong deterministic match overall.
    if len(usable) > 1 and conf < 90 and not fingerprint_matched(classification):
        return True, "multi_sheet_uncertain"

    return False, ""


def _llm_candidate_sheets(
    sheets: Sequence[Dict[str, Any]],
    winner: Optional[ParserResult],
) -> List[Dict[str, Any]]:
    """Rank candidate worksheets for LLM assist (best tabular signal first)."""
    from app.erp_parser.sheet_detector import score_sheet

    usable = [item for item in sheets if _sheet_has_usable_data(item)]
    ranked = sorted(
        usable,
        key=lambda item: score_sheet(item.get("matrix") or []),
        reverse=True,
    )
    if winner and winner.sheet_name:
        preferred = [item for item in ranked if item.get("sheet_name") == winner.sheet_name]
        others = [item for item in ranked if item.get("sheet_name") != winner.sheet_name]
        ranked = preferred + others
    return ranked[:3]


def _should_accept_llm(
    llm_result: Optional[ParserResult],
    winner: Optional[ParserResult],
) -> bool:
    """Accept a validated LLM mapping when deterministic result is absent or weaker."""
    if llm_result is None or not llm_result.rows:
        return False
    if winner is None or not winner.rows:
        return True
    if _mapping_incomplete(winner) and not _mapping_incomplete(llm_result):
        return True
    return float(llm_result.confidence or 0) >= float(winner.confidence or 0)


def _matching_profile(digest: str, known_profiles: Optional[Sequence[Dict[str, Any]]]) -> Optional[Dict[str, Any]]:
    """Return the saved layout whose fingerprint matches this workbook."""
    current = (digest or "").strip().upper()
    if not current or not known_profiles:
        return None
    for item in known_profiles:
        saved = str(item.get("fingerprint") or "").strip().upper()
        if saved and saved == current and float(item.get("confidence") or 0) >= 90:
            return item
    return None


def _best(results: Sequence[ParserResult]) -> Optional[ParserResult]:
    ranked = [item for item in results if item.rows]
    if not ranked:
        return None
    return max(ranked, key=lambda item: (item.confidence, len(item.rows)))


def _terminal_state(winner: Optional[ParserResult]) -> str:
    if winner is None or not winner.rows:
        return "Human Review Required"
    band = decision_band(winner.confidence)
    if band == "auto_accept":
        return "Parsed Successfully"
    if band == "accept_warning":
        return "Parsed with Warning"
    if band == "human_review":
        return "Human Review Required"
    if winner.confidence >= 95:
        return "Parsed Successfully"
    if winner.confidence >= 90:
        return "Parsed with Warning"
    return "Human Review Required"


def _score(result: ParserResult, **kwargs: Any) -> ParserResult:
    authored = float(result.confidence or 0)
    scored = score_extraction(result.rows, **kwargs)
    if result.parser_name == "email_body_matrix" and result.llm_used:
        result.confidence = min(97.0, max(85.0, authored))
    else:
        result.confidence = max(authored, scored)
    band = decision_band(result.confidence)
    result.warnings = [
        note
        for note in result.warnings
        if "Confidence is between" not in note and "Human review" not in note
    ]
    if band == "accept_warning":
        result.warnings.append("Accepted with warning. Confidence is between 90 and 94.")
    elif band == "human_review" and result.rows:
        result.warnings.append("Human review required. Confidence is below 70.")
    return result


def _merge_sheets(results: Sequence[ParserResult], **score_kwargs: Any) -> Optional[ParserResult]:
    used = [item for item in results if item.rows]
    if not used:
        return None
    if len(used) == 1:
        return _score(used[0], **score_kwargs)
    rows: List[Dict[str, Any]] = []
    qty_ok = qty_fail = skipped = 0
    names: List[str] = []
    for item in used:
        rows.extend(item.rows)
        if item.sheet_name and item.sheet_name not in names:
            names.append(item.sheet_name)
        qty_ok += int(item.extracted.get("quantity_ok") or 0)
        qty_fail += int(item.extracted.get("quantity_fail") or 0)
        skipped += int(item.extracted.get("skipped_invalid") or 0)
    dominant = max(used, key=lambda item: len(item.rows))
    merged = ParserResult(
        rows=rows,
        parser_name=dominant.parser_name,
        reason="; ".join(f"{item.sheet_name}: {item.parser_name}" for item in used),
        warnings=[note for item in used for note in item.warnings],
        extracted={
            **dominant.extracted,
            "rows": rows,
            "quantity_ok": qty_ok,
            "quantity_fail": qty_fail,
            "skipped_invalid": skipped,
            "layout": dominant.extracted.get("layout") or dominant.parser_name,
        },
        mapped=dominant.mapped,
        sheet_name=names[0] if names else dominant.sheet_name,
        header_row=dominant.header_row,
        sheet_score=dominant.sheet_score,
        confidence=float(dominant.confidence or 0),
    )
    return _score(merged, **score_kwargs)


class UniversalParserOrchestrator:
    """Select the highest-confidence parser for one workbook."""

    def __init__(self, parser: Any) -> None:
        self.parser = parser

    def parse(
        self,
        path: Union[str, Path],
        *,
        sheet_name: Optional[str] = None,
        distributor_label: str = "",
        reporting_quarter: Optional[str] = None,
        fiscal_year_start: Optional[int] = None,
        allow_llm_fallback: bool = True,
        subject: Optional[str] = None,
        preferred_parser: Optional[str] = None,
        known_fingerprint: Optional[str] = None,
        known_profiles: Optional[Sequence[Dict[str, Any]]] = None,
    ) -> Any:
        started = time.perf_counter()
        file_path = Path(path)
        logger.info("ERP parse start | path={}", file_path)

        if subject:
            from app.utils.email_subject_parser import try_parse_email_subject

            parsed_subject = try_parse_email_subject(subject)
            if parsed_subject:
                distributor_label = distributor_label or str(parsed_subject.get("distributor") or "")
                if not reporting_quarter:
                    reporting_quarter = parsed_subject.get("period")

        score_kwargs = {
            "distributor_label": distributor_label,
            "reporting_quarter": reporting_quarter,
            "fingerprint_matched": False,
        }
        run_kwargs = {
            "fiscal_year_start": fiscal_year_start,
            "reporting_quarter": reporting_quarter,
            "distributor_label": distributor_label,
        }

        fingerprint = None
        classification = None
        prepared = None
        try:
            prepared = run_bounded("loader", lambda: open_workbook_once(file_path))
            sheets = prepared.sheets
            if sheet_name:
                sheets = [item for item in sheets if item["sheet_name"] == sheet_name] or sheets
            fingerprint = run_bounded(
                "fingerprint",
                lambda: build_fingerprint(
                    file_path,
                    sheets,
                    merged_cells=prepared.merged_cells,
                ),
            )
            classification = run_bounded(
                "classifier", lambda: classify_workbook(sheets, fingerprint)
            )
        except StageTimeout:
            logger.info("{}\nFingerprint : {}", HUMAN_REVIEW_TIMEOUT, "")
            raise ExcelProcessingError(HUMAN_REVIEW_TIMEOUT) from None
        except ExcelProcessingError as exc:
            if "Invalid workbook" in str(exc):
                logger.info("Failed (Corrupted Workbook)\n{}", exc)
            raise

        saved = (known_fingerprint or "").strip().upper()
        matched_profile = _matching_profile(fingerprint.digest, known_profiles)
        if known_profiles:
            if matched_profile is not None:
                preferred_parser = str(matched_profile.get("parser") or "") or preferred_parser
            else:
                preferred_parser = None
        elif saved and saved != fingerprint.digest:
            logger.info(
                "Parser profile fingerprint changed | saved={} | current={}",
                saved,
                fingerprint.digest,
            )
            preferred_parser = None
        score_kwargs["fingerprint_matched"] = fingerprint_matched(classification)

        candidates = list(prepared.candidate_sheets if prepared is not None else [])

        def _select() -> Optional[ParserResult]:
            chosen: Optional[ParserResult] = None
            if preferred_parser:
                chosen = self._evaluate(
                    file_path,
                    sheets,
                    only=preferred_parser,
                    run_kwargs=run_kwargs,
                    score_kwargs=score_kwargs,
                    raw_matrices=prepared.raw_matrices if prepared is not None else None,
                    sheet_names=prepared.candidate_sheets if prepared is not None else None,
                )
                if chosen is None or chosen.confidence < 90:
                    logger.info(
                        "Parser profile fallback | preferred={} | confidence={}",
                        preferred_parser,
                        None if chosen is None else chosen.confidence,
                    )
                    chosen = self._evaluate(
                        file_path,
                        sheets,
                        only=None,
                        run_kwargs=run_kwargs,
                        score_kwargs=score_kwargs,
                        raw_matrices=prepared.raw_matrices if prepared is not None else None,
                        sheet_names=prepared.candidate_sheets if prepared is not None else None,
                    )
            else:
                chosen = self._evaluate(
                    file_path,
                    sheets,
                    only=None,
                    run_kwargs=run_kwargs,
                    score_kwargs=score_kwargs,
                    raw_matrices=prepared.raw_matrices if prepared is not None else None,
                    sheet_names=prepared.candidate_sheets if prepared is not None else None,
                )
            return chosen

        scoring_timed_out = False
        try:
            winner = run_bounded("scoring", _select)
        except StageTimeout:
            # Do not abandon usable workbooks before LLM fallback has a chance.
            scoring_timed_out = True
            winner = None
            logger.warning(
                "Deterministic scoring timed out; attempting LLM fallback | fingerprint={}",
                fingerprint.digest,
            )

        llm_tokens = 0
        llm_reason = ""
        mapping_source = "python"
        need_llm, fallback_reason = _needs_llm_fallback(winner, sheets, classification)
        if scoring_timed_out and any(_sheet_has_usable_data(item) for item in sheets):
            need_llm = True
            fallback_reason = fallback_reason or "scoring_timeout"

        if allow_llm_fallback and need_llm and sheets:
            det_conf = float(winner.confidence or 0) if winner is not None else 0.0
            llm_reason = (
                "Unknown ERP Layout"
                if classification.parser_name == "unknown"
                else (
                    f"Low confidence {PARSER_LABEL.get(winner.parser_name, winner.parser_name)}"
                    if winner is not None
                    else "No valid deterministic layout"
                )
            )
            llm_sheets = _llm_candidate_sheets(sheets, winner)
            llm_result: Optional[ParserResult] = None
            accepted = False
            for llm_sheet in llm_sheets:
                logger.info(
                    "LLM Fallback Triggered | file={} | sheet={} | reason={} | "
                    "accuracy={} | deterministic_confidence={}",
                    file_path.name,
                    llm_sheet.get("sheet_name"),
                    fallback_reason,
                    int(round(det_conf)),
                    round(det_conf, 1),
                )
                try:
                    llm_result, llm_tokens = run_bounded(
                        "llm",
                        lambda sheet=llm_sheet: self._semantic_resolve(
                            sheet,
                            reason=llm_reason,
                            run_kwargs=run_kwargs,
                            score_kwargs=score_kwargs,
                            sheet_candidates=run_sheet_candidates(
                                sheet["matrix"],
                                sheet["sheet_name"],
                                **run_kwargs,
                            ),
                            fingerprint=fingerprint,
                        ),
                    )
                except StageTimeout:
                    logger.warning(
                        "LLM Structure Assist unavailable | human review | fingerprint={} | sheet={}",
                        fingerprint.digest,
                        llm_sheet.get("sheet_name"),
                    )
                    llm_result = None
                    continue

                mapped = (llm_result.mapped or {}) if llm_result is not None else {}
                llm_conf = float(
                    (mapped.get("llm_confidence") if mapped else None)
                    or (llm_result.confidence if llm_result is not None else 0)
                    or 0
                )
                model_name = (
                    getattr(llm_result, "llm_model", None) if llm_result is not None else None
                ) or ""
                final_map = {
                    "customer": (mapped.get("originals") or {}).get("customer"),
                    "product": (mapped.get("originals") or {}).get("product"),
                    "quantity": (mapped.get("originals") or {}).get("quantity"),
                }
                rows_n = len(llm_result.rows) if llm_result is not None else 0
                if _should_accept_llm(llm_result, winner):
                    assert llm_result is not None
                    llm_result.llm_used = True
                    llm_result.llm_tokens = llm_tokens
                    llm_result.llm_reason = f"{llm_reason} ({fallback_reason})"
                    winner = llm_result
                    mapping_source = "llm"
                    accepted = True
                    logger.info(
                        "LLM Fallback Triggered | result=accepted | file={} | sheet={} | "
                        "reason={} | selected_model={} | llm_confidence={} | "
                        "final_mapping={} | rows_extracted={}",
                        file_path.name,
                        llm_sheet.get("sheet_name"),
                        fallback_reason,
                        model_name,
                        round(llm_conf, 1),
                        final_map,
                        rows_n,
                    )
                    break

                logger.info(
                    "LLM Fallback Triggered | result=rejected | file={} | sheet={} | "
                    "reason={} | selected_model={} | llm_confidence={} | "
                    "final_mapping={} | rows_extracted={}",
                    file_path.name,
                    llm_sheet.get("sheet_name"),
                    fallback_reason,
                    model_name,
                    round(llm_conf, 1),
                    final_map,
                    rows_n,
                )

            if not accepted and winner is not None:
                winner.llm_used = True
                winner.llm_tokens = llm_tokens
                winner.llm_reason = llm_reason or "Bedrock unavailable"
                if scoring_timed_out or llm_result is None:
                    winner.warnings.append(
                        "Human review required. Structure assist was unavailable."
                    )

        if winner is None or not winner.rows:
            logger.info(
                "Human Review Required\n\nReason : Unsupported Workbook Structure\n\nFingerprint : {}\nConfidence : {}",
                fingerprint.digest,
                int(round(classification.confidence)),
            )
            raise ExcelProcessingError(_COULD_NOT_MAP)

        quarter = (reporting_quarter or "").strip()
        if quarter:
            for row in winner.rows:
                if not str(row.get("period") or "").strip():
                    row["period"] = quarter
                    row["reporting_quarter"] = quarter
        _score(winner, **score_kwargs)
        winner.parser_version = winner.parser_version or parser_version(winner.parser_name)
        winner.layout = winner.layout or classification.layout_name
        duration = time.perf_counter() - started
        self._log_selected(file_path, winner, distributor_label, duration)
        confidence = self._publish_confidence(winner)
        result = self.parser._finalize_result(
            chosen=winner.sheet_name or (candidates[0] if candidates else file_path.stem),
            sheet_score=winner.sheet_score,
            header_row=winner.header_row,
            active_mapped=winner.mapped or _empty_mapped(),
            active_extracted=winner.extracted,
            confidence=confidence,
            mapping_source=mapping_source,
            candidates=candidates,
            distributor_label=distributor_label or str(winner.extracted.get("distributor") or ""),
            reporting_quarter=reporting_quarter,
            python_overall=float(winner.confidence),
        )
        breakdown = dict(result.confidence_breakdown or {})
        state = _terminal_state(winner)
        layout_name = (
            str(winner.extracted.get("layout") or winner.layout)
            if winner.parser_name in {"pdf_stock_register", "email_body_matrix"}
            else classification.layout_name
        )
        breakdown.update(
            {
                "parser_name": winner.parser_name,
                "parser_label": PARSER_LABEL.get(winner.parser_name, winner.parser_name),
                "parser_version": winner.parser_version,
                "layout": winner.extracted.get("layout") or winner.layout,
                "layout_name": layout_name,
                "layout_reason": classification.reason,
                "fingerprint": fingerprint.digest,
                "fingerprint_payload": fingerprint.as_dict(),
                "terminal_state": state,
                "orchestrator_confidence": winner.confidence,
                "llm_used": winner.llm_used,
                "llm_tokens": winner.llm_tokens,
                "llm_reason": winner.llm_reason,
                "llm_model": winner.llm_model,
                "warnings": winner.warnings,
                "sheet_count": len(sheets),
                "duration_sec": round(duration, 2),
                "decision": decision_band(winner.confidence),
            }
        )
        result.confidence_breakdown = breakdown
        self._audit_log(
            email_name=distributor_label or file_path.stem,
            sheet_count=len(sheets),
            winner=winner,
            duration=duration,
            fingerprint=fingerprint.digest,
            layout_name=layout_name,
        )
        return result

    def _evaluate(
        self,
        path: Path,
        sheets: Sequence[Dict[str, Any]],
        *,
        only: Optional[str],
        run_kwargs: Dict[str, Any],
        score_kwargs: Dict[str, Any],
        raw_matrices: Optional[Dict[str, Any]] = None,
        sheet_names: Optional[Sequence[str]] = None,
    ) -> Optional[ParserResult]:
        from app.erp_parser.sheet_detector import score_sheet

        # Inspect every worksheet. Higher-scoring sheets first so a valid
        # "Data" tab is not starved when earlier cover sheets are empty/noisy.
        ordered = sorted(
            sheets,
            key=lambda item: score_sheet(item.get("matrix") or []),
            reverse=True,
        )
        per_sheet: List[ParserResult] = []
        for sheet in ordered:
            found = run_sheet_candidates(
                sheet["matrix"],
                sheet["sheet_name"],
                only=only,
                **run_kwargs,
            )
            for item in found:
                _score(item, **score_kwargs)
            fingerprints = fingerprint_sheet(sheet["matrix"])
            hint = ", ".join(fp["layout"] for fp in fingerprints if fp["fingerprint_confidence"] >= 90)
            best = _best(found)
            if best is not None:
                if hint:
                    best.reason = f"{hint}. {best.reason}"
                best.sheet_score = max(
                    float(best.sheet_score or 0),
                    score_sheet(sheet.get("matrix") or []),
                )
                per_sheet.append(best)
                logger.info(
                    "Sheet candidate | sheet={} | parser={} | rows={} | confidence={}",
                    best.sheet_name,
                    best.parser_name,
                    len(best.rows),
                    round(float(best.confidence or 0), 1),
                )

        # One best worksheet for standard layouts (do not merge unrelated sheets).
        best_sheet = _best(per_sheet)
        monthly: Optional[ParserResult] = None
        if only in (None, "monthly_product_sheets"):
            monthly = run_monthly_sheets(
                path,
                raw_matrices=raw_matrices,
                sheet_names=sheet_names,
                **run_kwargs,
            )
            _score(monthly, **score_kwargs)
            if not monthly.rows:
                monthly = None
        options = [item for item in (best_sheet, monthly) if item is not None and item.rows]
        return _best(options)

    def _semantic_resolve(
        self,
        sheet: Dict[str, Any],
        *,
        reason: str,
        run_kwargs: Dict[str, Any],
        score_kwargs: Dict[str, Any],
        sheet_candidates: Sequence[ParserResult],
        fingerprint: Any = None,
    ) -> tuple[Optional[ParserResult], int]:
        matrix = sheet["matrix"]
        header_idx = 0
        best_density = -1
        for idx, row in enumerate(matrix[:20]):
            density = sum(1 for cell in row if _textish(cell))
            if density > best_density:
                best_density = density
                header_idx = idx
        header_row = list(matrix[header_idx]) if matrix else []
        headers = [str(cell).strip() for cell in header_row if _textish(cell)][:15]
        samples: List[List[str]] = []
        width = max(len(header_row), max((len(row) for row in matrix), default=0))
        for row in matrix[header_idx + 1 :]:
            if not any(cell not in (None, "") for cell in row):
                continue
            samples.append(["" if cell is None else str(cell)[:80] for cell in list(row)[:width]])
            if len(samples) >= 5:
                break
        title_rows: List[List[str]] = []
        for row in matrix[:header_idx]:
            texts = [str(cell).strip()[:80] for cell in row if _textish(cell)]
            if texts:
                title_rows.append(texts[:8])
            if len(title_rows) >= 5:
                break
        stats = {
            "sheet_name": sheet["sheet_name"],
            "row_count": len(matrix),
            "column_count": max((len(row) for row in matrix), default=0),
            "non_empty_rows": sum(1 for row in matrix if any(cell not in (None, "") for cell in row)),
            "detected_headers": headers,
            "title_rows": title_rows,
        }
        resolver = LLMHeaderResolver(timeout=30)
        started_llm = time.perf_counter()
        try:
            llm = resolver.resolve_headers(
                headers,
                samples,
                sample_limit=5,
                system_prompt=SEMANTIC_PROMPT,
                extra={
                    "metadata": stats,
                    "sheet_statistics": stats,
                    "fingerprint": fingerprint.as_dict() if fingerprint is not None else {},
                    "sheet_names": [sheet["sheet_name"]],
                    "merged_cells": int(getattr(fingerprint, "merged_cells", 0) or 0),
                    "reason": reason,
                    "title_rows": title_rows,
                },
            )
        except LLMHeaderResolverError as exc:
            logger.warning("LLM Semantic Resolver failed | err={}", exc)
            return None, int(getattr(resolver, "last_token_count", 0) or 0)
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM Semantic Resolver failed | err={}", exc)
            return None, int(getattr(resolver, "last_token_count", 0) or 0)

        tokens = int(getattr(resolver, "last_token_count", 0) or 0)
        prompt_tokens = int(getattr(resolver, "last_prompt_tokens", 0) or 0)
        completion_tokens = int(getattr(resolver, "last_completion_tokens", 0) or 0)
        from app.llm.model_registry import display_name_for
        from app.erp_parser.parser_service import (
            LLM_MIN_TRUST,
            _apply_llm_column_map,
            _find_header_row_for_llm_labels,
            _mapping_complete,
        )
        from app.erp_parser.row_extractor import extract_rows

        model_label = display_name_for(getattr(resolver, "last_model_id", None))
        llm_conf = float(llm.get("confidence") or 0)
        logger.info(
            "LLM Structure Assist\n\nReason : {}\n\nModel : {}\nInput Tokens : {}\nOutput Tokens : {}\nReturned Layout : {}\nLLM Confidence : {}\nDuration : {:.2f} sec",
            reason,
            model_label,
            prompt_tokens,
            completion_tokens,
            llm.get("layout_type") or llm.get("parser_hint") or "",
            int(round(llm_conf)),
            time.perf_counter() - started_llm,
        )
        if llm.get("is_sales_table") is False:
            logger.info(
                "LLM Semantic Resolver rejected sheet as non-sales | sheet={}",
                sheet["sheet_name"],
            )
            return None, tokens
        if llm_conf < LLM_MIN_TRUST:
            logger.info(
                "LLM Semantic Resolver confidence below trust floor | llm={} | sheet={}",
                llm_conf,
                sheet["sheet_name"],
            )
            return None, tokens

        hinted = extract_with_layout(
            sheet,
            llm,
            run_kwargs=run_kwargs,
            sheet_candidates=sheet_candidates,
        )
        if hinted is not None:
            _score(hinted, **score_kwargs)

        use_idx = _find_header_row_for_llm_labels(matrix, llm)
        if use_idx is None:
            use_idx = header_idx
        use_header = list(matrix[use_idx]) if matrix else header_row
        remapped = _apply_llm_column_map(use_header, llm, python_mapped={})

        # Reject hallucinated column labels that do not exist on the worksheet.
        for field, key in (
            ("customer", "customer_column"),
            ("product", "product_column"),
            ("quantity", "quantity_column"),
        ):
            label = llm.get(key)
            if label and remapped["positions"].get(field) is None:
                logger.warning(
                    "LLM Semantic Resolver rejected hallucinated column | field={} | label={} | sheet={}",
                    field,
                    label,
                    sheet["sheet_name"],
                )
                return None, tokens

        title_product = str(llm.get("product_from_title") or "").strip()
        extracted_result: Optional[ParserResult] = None
        positions = dict(remapped["positions"])
        work_matrix: Sequence[Sequence[Any]] = matrix
        if title_product and positions.get("product") is None and positions.get("customer") is not None:
            # extract_rows requires a product column index — inject title as a constant column.
            expanded = [list(row) for row in matrix]
            prod_col = max((len(row) for row in expanded), default=0)
            for idx, row in enumerate(expanded):
                while len(row) <= prod_col:
                    row.append(None)
                if idx == use_idx:
                    row[prod_col] = "Product"
                elif idx > use_idx:
                    row[prod_col] = title_product
            work_matrix = expanded
            positions["product"] = prod_col
            remapped = {
                **remapped,
                "positions": positions,
                "originals": {
                    **(remapped.get("originals") or {}),
                    "product": title_product,
                },
                "confidences": {
                    **(remapped.get("confidences") or {}),
                    "product": llm_conf,
                },
                "methods": {
                    **(remapped.get("methods") or {}),
                    "product": "llm_title",
                },
            }

        mapping_ok = _mapping_complete(positions, remapped.get("quantity_columns") or [])
        if mapping_ok:
            try:
                extracted = extract_rows(
                    work_matrix,
                    header_row_index=use_idx,
                    positions=positions,
                    quantity_columns=remapped.get("quantity_columns") or None,
                    month_column_meta=remapped.get("month_column_meta") or None,
                    fiscal_year_start=run_kwargs.get("fiscal_year_start"),
                    reporting_quarter=run_kwargs.get("reporting_quarter"),
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("LLM Semantic Resolver extract failed | err={}", exc)
                extracted = None
            if extracted and extracted.get("rows"):
                extracted["layout"] = "header"
                extracted["header_row"] = use_idx + 1
                extracted_result = ParserResult(
                    rows=list(extracted["rows"]),
                    parser_name="header",
                    reason=reason,
                    extracted=extracted,
                    mapped=remapped,
                    sheet_name=sheet["sheet_name"],
                    header_row=use_idx + 1,
                    llm_used=True,
                    llm_reason=reason,
                )
                _score(extracted_result, **score_kwargs)

        options = [item for item in (hinted, extracted_result) if item is not None and item.rows]
        chosen = _best(options)
        if chosen is not None:
            chosen.llm_used = True
            chosen.llm_tokens = tokens
            chosen.llm_reason = reason
            chosen.llm_model = model_label
        return chosen, tokens

    def _publish_confidence(self, winner: ParserResult) -> Dict[str, Any]:
        field_conf = dict((winner.mapped or {}).get("confidences") or {})
        if not field_conf:
            field_conf = {"customer": 0.0, "product": 0.0, "quantity": 0.0}
        confidence = compute_erp_confidence(
            field_confidences=field_conf,
            sheet_score=winner.sheet_score,
            extracted_rows=len(winner.rows),
            quantity_ok=int(winner.extracted.get("quantity_ok") or len(winner.rows)),
            quantity_fail=int(winner.extracted.get("quantity_fail") or 0),
            skipped_invalid=int(winner.extracted.get("skipped_invalid") or 0),
        )
        published = float(winner.confidence)
        band = "green" if published >= 90 else "yellow" if published >= 75 else "red"
        confidence["overall_confidence"] = published
        confidence["accuracy"] = published
        confidence["band"] = band
        confidence["orchestrator_confidence"] = published
        confidence["llm_used"] = winner.llm_used
        return confidence

    def _log_selected(
        self,
        path: Path,
        winner: ParserResult,
        distributor_label: str,
        duration: float = 0.0,
    ) -> None:
        label = PARSER_LABEL.get(winner.parser_name, winner.parser_name)
        extracted = winner.extracted
        if winner.parser_name == "metadata":
            logger.info(
                "ERP Strategy: Metadata Parser\nDistributor: {}\nProduct: {}\nRows: {}",
                distributor_label or extracted.get("distributor") or "",
                extracted.get("product") or "",
                len(winner.rows),
            )
        elif winner.parser_name == "stock_item_register":
            logger.info(
                "ERP Strategy : Stock Item Register Parser\nDistributor : {}\nProduct : {}\nQuarter : {}\nRows Parsed : {}",
                distributor_label or extracted.get("distributor") or "",
                extracted.get("product") or "",
                extracted.get("quarter") or "",
                len(winner.rows),
            )
        elif winner.parser_name == "product_blocks":
            logger.info(
                "ERP Block Parser activated\nfile={}\nproducts_detected={}\nrows_extracted={}",
                path.name,
                int(extracted.get("products_detected") or 0),
                len(winner.rows),
            )
        elif winner.parser_name == "cross_product_matrix":
            logger.info(
                "Parser : Cross Product Matrix\nStrategy : Product Block Matrix\nProducts : {}\nCustomers : {}\nRows Parsed : {}\nQuarter : {}\nConfidence : {}\nLLM Used : {}",
                int(extracted.get("products_detected") or 0),
                int(extracted.get("customers_detected") or 0),
                len(winner.rows),
                extracted.get("quarter") or "",
                int(round(winner.confidence)),
                "Yes" if winner.llm_used else "No",
            )
        elif winner.parser_name == "matrix_month":
            months = extracted.get("months_detected") or []
            logger.info(
                "ERP Strategy : Matrix Month Parser\nDistributor : {}\nRows Parsed : {}\nMonths Detected : {}\nQuarter : {}\nLLM Used : {}",
                distributor_label or extracted.get("distributor") or "",
                len(winner.rows),
                ", ".join(str(item) for item in months),
                extracted.get("quarter") or "",
                "True" if winner.llm_used else "False",
            )
        elif winner.parser_name == "email_body_matrix":
            products = {
                str(row.get("product") or "").strip()
                for row in winner.rows
                if str(row.get("product") or "").strip()
            }
            customers = {
                str(row.get("customer_name") or "").strip()
                for row in winner.rows
                if str(row.get("customer_name") or "").strip()
            }
            logger.info(
                "AI Job\n\nDocument Type : Email Body\n\nParser : Email Body Matrix\n\nProducts : {}\n\nCustomers : {}\n\nRows Parsed : {}\n\nQuarter : {}\n\nConfidence : {}\n\nLLM Used : {}\n\nDuration : {:.2f} sec",
                int(winner.extracted.get("products_detected") or len(products)),
                int(winner.extracted.get("customers_detected") or len(customers)),
                len(winner.rows),
                winner.extracted.get("quarter") or "",
                int(round(winner.confidence)),
                "Yes" if winner.llm_used else "No",
                duration,
            )
            logger.info(
                "Business Matrix = Yes\nGPT Invoked = {}\nRows Parsed = {}\nQueue Status = Success\nImport Status = Completed",
                "Yes" if winner.llm_used else "No",
                len(winner.rows),
            )
        elif winner.parser_name == "pdf_stock_register":
            from app.erp_parser.documents.row_quarters import quarter_split

            customers = {
                str(row.get("customer_name") or "").strip()
                for row in winner.rows
                if str(row.get("customer_name") or "").strip()
            }
            split = quarter_split(winner.rows)
            split_lines = "\n".join(f"{name} : {count}" for name, count in sorted(split.items())) or "—"
            logger.info(
                "Parser : PDF Stock Register\n\nCustomers : {}\n\nRows Parsed : {}\n\nQuarter Split\n{}\n\nConfidence : {}\n\nLLM Used : {}",
                int(winner.extracted.get("customers_detected") or len(customers)),
                len(winner.rows),
                split_lines,
                int(round(winner.confidence)),
                "Yes" if winner.llm_used else "No",
            )
        else:
            logger.info(
                "ERP Strategy : {}\nRows : {}\nConfidence : {}",
                label,
                len(winner.rows),
                winner.confidence,
            )

    def _audit_log(
        self,
        *,
        email_name: str,
        sheet_count: int,
        winner: ParserResult,
        duration: float,
        fingerprint: str = "",
        layout_name: str = "",
    ) -> None:
        label = PARSER_LABEL.get(winner.parser_name, winner.parser_name)
        logger.info(
            "AI Job\n\nDistributor : {}\n\nLayout : {}\n\nFingerprint : {}\n\nParser : {}\n\nVersion : {}\n\nConfidence : {}\n\nLLM Used : {}\n\nRows Parsed : {}\n\nDuration : {:.2f} sec",
            email_name or "Email",
            layout_name or winner.layout or label,
            fingerprint,
            label,
            winner.parser_version or parser_version(winner.parser_name),
            int(round(winner.confidence)),
            "Yes" if winner.llm_used else "No",
            len(winner.rows),
            duration,
        )
        if sheet_count:
            logger.info("Sheets : {}", sheet_count)


def _empty_mapped() -> Dict[str, Any]:
    return {
        "positions": {"customer": None, "product": None, "quantity": None},
        "originals": {},
        "confidences": {},
        "methods": {},
        "quantity_columns": [],
        "month_column_meta": [],
    }


def _textish(cell: Any) -> bool:
    if cell is None:
        return False
    text = str(cell).strip()
    if not text:
        return False
    compact = text.replace(".", "", 1).replace("-", "", 1)
    return not compact.isdigit()
