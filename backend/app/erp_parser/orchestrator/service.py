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
    PRIORITY,
    run_monthly_sheets,
    run_sheet_candidates,
)
from app.erp_parser.orchestrator.confidence_engine import decision_band, score_extraction
from app.erp_parser.orchestrator.detector import fingerprint_sheet
from app.erp_parser.orchestrator.normalizer import normalize_workbook
from app.erp_parser.orchestrator.types import ParserResult
from app.erp_parser.workbook_detector import detect_workbook
from app.exceptions import ExcelProcessingError

logger = get_logger(__name__)

_COULD_NOT_MAP = (
    "Could not map Customer, Product, and Sales Quantity columns. "
    "Please verify the ERP export has recognizable headers."
)

SEMANTIC_PROMPT = """You are an ERP semantic column mapping engine.

You will receive metadata, column headers, at most 5 sample rows, and sheet statistics.
Do not extract rows. Do not infer quantities. Do not rewrite cells.

Return JSON only:
{
  "customer_column": "",
  "product_column": "",
  "quantity_column": "",
  "parser_hint": "",
  "confidence": 0
}

parser_hint must be one of: header, matrix_month, stock_item_register, metadata, product_blocks.
Use null when a column is uncertain. Confidence is 0-100.
"""


def _best(results: Sequence[ParserResult]) -> Optional[ParserResult]:
    ranked = [item for item in results if item.rows]
    if not ranked:
        return None
    return max(ranked, key=lambda item: (item.confidence, PRIORITY.get(item.parser_name, 0)))


def _score(result: ParserResult, **kwargs: Any) -> ParserResult:
    authored = float(result.confidence or 0)
    result.confidence = max(authored, score_extraction(result.rows, **kwargs))
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
        }
        run_kwargs = {
            "fiscal_year_start": fiscal_year_start,
            "reporting_quarter": reporting_quarter,
            "distributor_label": distributor_label,
        }

        sheets = normalize_workbook(file_path)
        if sheet_name:
            sheets = [item for item in sheets if item["sheet_name"] == sheet_name] or sheets
        wb_info = detect_workbook(file_path)
        candidates = list(wb_info.get("candidate_sheets") or [])

        winner: Optional[ParserResult] = None
        if preferred_parser:
            winner = self._evaluate(file_path, sheets, only=preferred_parser, run_kwargs=run_kwargs, score_kwargs=score_kwargs)
            if winner is None or winner.confidence < 90:
                logger.info(
                    "Parser profile fallback | preferred={} | confidence={}",
                    preferred_parser,
                    None if winner is None else winner.confidence,
                )
                winner = self._evaluate(file_path, sheets, only=None, run_kwargs=run_kwargs, score_kwargs=score_kwargs)
        else:
            winner = self._evaluate(file_path, sheets, only=None, run_kwargs=run_kwargs, score_kwargs=score_kwargs)

        llm_tokens = 0
        llm_reason = ""
        mapping_source = "python"
        if (
            winner is not None
            and allow_llm_fallback
            and decision_band(winner.confidence) == "llm"
            and sheets
        ):
            weakest = min(sheets, key=lambda item: len(item["matrix"]))
            llm_result, llm_tokens = self._semantic_resolve(
                weakest,
                reason=f"Low confidence {PARSER_LABEL.get(winner.parser_name, winner.parser_name)}",
                run_kwargs=run_kwargs,
                score_kwargs=score_kwargs,
                sheet_candidates=run_sheet_candidates(
                    weakest["matrix"],
                    weakest["sheet_name"],
                    **run_kwargs,
                ),
            )
            llm_reason = f"Low confidence {PARSER_LABEL.get(winner.parser_name, winner.parser_name)}"
            if llm_result is not None and llm_result.confidence > winner.confidence:
                llm_result.llm_used = True
                llm_result.llm_tokens = llm_tokens
                llm_result.llm_reason = llm_reason
                winner = llm_result
                mapping_source = "llm"
            else:
                winner.llm_used = True
                winner.llm_tokens = llm_tokens
                winner.llm_reason = llm_reason

        if winner is None or not winner.rows:
            raise ExcelProcessingError(_COULD_NOT_MAP)

        quarter = (reporting_quarter or "").strip()
        if quarter:
            for row in winner.rows:
                if not str(row.get("period") or "").strip():
                    row["period"] = quarter
                    row["reporting_quarter"] = quarter
        _score(winner, **score_kwargs)
        self._log_selected(file_path, winner, distributor_label)
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
        duration = time.perf_counter() - started
        breakdown = dict(result.confidence_breakdown or {})
        breakdown.update(
            {
                "parser_name": winner.parser_name,
                "parser_label": PARSER_LABEL.get(winner.parser_name, winner.parser_name),
                "orchestrator_confidence": winner.confidence,
                "llm_used": winner.llm_used,
                "llm_tokens": winner.llm_tokens,
                "llm_reason": winner.llm_reason,
                "warnings": winner.warnings,
                "sheet_count": len(sheets),
                "duration_sec": round(duration, 1),
                "decision": decision_band(winner.confidence),
            }
        )
        result.confidence_breakdown = breakdown
        self._audit_log(
            email_name=distributor_label or file_path.stem,
            sheet_count=len(sheets),
            winner=winner,
            duration=duration,
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
    ) -> Optional[ParserResult]:
        per_sheet: List[ParserResult] = []
        for sheet in sheets:
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
                per_sheet.append(best)
        merged = _merge_sheets(per_sheet, **score_kwargs)
        monthly: Optional[ParserResult] = None
        if only in (None, "monthly_product_sheets"):
            monthly = run_monthly_sheets(path, **run_kwargs)
            _score(monthly, **score_kwargs)
            if not monthly.rows:
                monthly = None
        options = [item for item in (merged, monthly) if item is not None and item.rows]
        return _best(options)

    def _semantic_resolve(
        self,
        sheet: Dict[str, Any],
        *,
        reason: str,
        run_kwargs: Dict[str, Any],
        score_kwargs: Dict[str, Any],
        sheet_candidates: Sequence[ParserResult],
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
        width = len(header_row)
        for row in matrix[header_idx + 1 :]:
            if not any(cell not in (None, "") for cell in row):
                continue
            samples.append(["" if cell is None else str(cell)[:80] for cell in list(row)[:width]])
            if len(samples) >= 5:
                break
        stats = {
            "sheet_name": sheet["sheet_name"],
            "row_count": len(matrix),
            "column_count": max((len(row) for row in matrix), default=0),
            "non_empty_rows": sum(1 for row in matrix if any(cell not in (None, "") for cell in row)),
        }
        resolver = LLMHeaderResolver()
        try:
            llm = resolver.resolve_headers(
                headers,
                samples,
                sample_limit=5,
                system_prompt=SEMANTIC_PROMPT,
                extra={"metadata": stats, "sheet_statistics": stats},
            )
        except LLMHeaderResolverError as exc:
            logger.warning("LLM Semantic Resolver failed | err={}", exc)
            return None, int(getattr(resolver, "last_token_count", 0) or 0)
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM Semantic Resolver failed | err={}", exc)
            return None, int(getattr(resolver, "last_token_count", 0) or 0)

        tokens = int(getattr(resolver, "last_token_count", 0) or 0)
        from app.erp_parser.parser_service import (
            _apply_llm_column_map,
            _find_header_row_for_llm_labels,
            _mapping_complete,
        )
        from app.erp_parser.row_extractor import extract_rows

        hint = str(llm.get("parser_hint") or "").strip()
        hinted = next((item for item in sheet_candidates if item.parser_name == hint and item.rows), None)
        if hinted is not None:
            _score(hinted, **score_kwargs)

        use_idx = _find_header_row_for_llm_labels(matrix, llm)
        if use_idx is None:
            use_idx = header_idx
        use_header = list(matrix[use_idx]) if matrix else header_row
        remapped = _apply_llm_column_map(use_header, llm, python_mapped={})
        extracted_result: Optional[ParserResult] = None
        if _mapping_complete(remapped["positions"], remapped.get("quantity_columns") or []):
            try:
                extracted = extract_rows(
                    matrix,
                    header_row_index=use_idx,
                    positions=remapped["positions"],
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

    def _log_selected(self, path: Path, winner: ParserResult, distributor_label: str) -> None:
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
        else:
            logger.info(
                "ERP Strategy : {}\nRows : {}\nConfidence : {}",
                label,
                len(winner.rows),
                winner.confidence,
            )

    def _audit_log(self, *, email_name: str, sheet_count: int, winner: ParserResult, duration: float) -> None:
        label = PARSER_LABEL.get(winner.parser_name, winner.parser_name)
        logger.info(
            "AI Job\nEmail\n{}\nAttachments : {}\nSheets : {}\nParser : {}\nConfidence : {}\nRows : {}\nLLM Used : {}\nDuration : {} sec",
            email_name or "Email",
            1,
            sheet_count,
            label,
            int(round(winner.confidence)),
            len(winner.rows),
            "Yes" if winner.llm_used else "No",
            f"{duration:.1f}",
        )
        if winner.llm_used:
            logger.info(
                "LLM Tokens\n{}\nReason\n{}",
                int(winner.llm_tokens or 0),
                winner.llm_reason or f"Low confidence {label}",
            )


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
