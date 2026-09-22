"""Detect reporting quarter from ERP workbook metadata (deterministic + optional LLM)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.erp_parser.fiscal_quarters import month_key_to_quarter, quarter_label
from app.erp_parser.workbook_detector import list_candidate_sheets, read_sheet_matrix
from app.utils.period_calendar import parse_month_label, parse_quarter_label

logger = get_logger(__name__)

OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"

# Apr-Jun 2026, Jul-Sep 2026, July 2026, Q2 2026, Secondary Sales Jul-Sep 2026
_RANGE_RE = re.compile(
    r"(?i)(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|"
    r"nov(?:ember)?|dec(?:ember)?)"
    r"\s*[-–—/to]+\s*"
    r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|"
    r"nov(?:ember)?|dec(?:ember)?)"
    r"[\s,]*(\d{4})"
)
_SINGLE_MONTH_RE = re.compile(
    r"(?i)\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|"
    r"nov(?:ember)?|dec(?:ember)?)\b[\s,]*(\d{4})"
)
_Q_LABEL_RE = re.compile(r"(?i)\bQ([1-4])\s+(\d{4})\b")
# FY 2025-26 • Q2  |  Q2 FY 2025-26
_FY_Q_RE = re.compile(
    r"(?i)\b(?:Q\s*([1-4])\s+)?FY\s*(\d{4})\s*[-–—/]\s*(\d{2}|\d{4})"
    r"(?:\s*[•·.\-]?\s*Q\s*([1-4]))?\b"
)

_MONTH_CANON = {
    "jan": "january",
    "january": "january",
    "feb": "february",
    "february": "february",
    "mar": "march",
    "march": "march",
    "apr": "april",
    "april": "april",
    "may": "may",
    "jun": "june",
    "june": "june",
    "jul": "july",
    "july": "july",
    "aug": "august",
    "august": "august",
    "sep": "september",
    "sept": "september",
    "september": "september",
    "oct": "october",
    "october": "october",
    "nov": "november",
    "november": "november",
    "dec": "december",
    "december": "december",
}


def _canon_month(token: str) -> str:
    return _MONTH_CANON.get((token or "").strip().lower(), (token or "").strip().lower())


def _month_num(token: str) -> Optional[int]:
    key = _canon_month(token)
    mapping = {
        "january": 1,
        "february": 2,
        "march": 3,
        "april": 4,
        "may": 5,
        "june": 6,
        "july": 7,
        "august": 8,
        "september": 9,
        "october": 10,
        "november": 11,
        "december": 12,
    }
    return mapping.get(key)


def _fy_quarter_from_months(start_m: int, end_m: int, year: int) -> Optional[str]:
    """Map month range to APCOTEX FY quarter (uses start month)."""
    sm = start_m if isinstance(start_m, int) else _month_num(str(start_m))
    if not sm:
        return None
    month_names = [
        "january", "february", "march", "april", "may", "june",
        "july", "august", "september", "october", "november", "december",
    ]
    start_key = month_names[sm - 1]
    q = month_key_to_quarter(start_key)
    if not q:
        return None
    fy_start = year if q != 4 else year - 1
    return quarter_label(fy_start, q)


def _score_candidate(label: str, confidence: float, source: str) -> Dict[str, Any]:
    return {
        "reporting_quarter": label,
        "confidence": round(confidence, 2),
        "source": source,
    }


def _scan_text(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    t = str(text).strip()

    m = _FY_Q_RE.search(t)
    if m:
        fy_start = int(m.group(2))
        quarter = m.group(1) or m.group(4)
        if quarter:
            label = quarter_label(fy_start, int(quarter))
            return _score_candidate(label, 99.0, "explicit_fy_quarter")
        # Annual FY mention alone is not a quarter — fall through

    m = _Q_LABEL_RE.search(t)
    if m:
        label = f"Q{m.group(1)} {m.group(2)}"
        parsed = parse_quarter_label(label)
        if parsed:
            return _score_candidate(parsed.label, 98.0, "explicit_quarter_label")

    m = _RANGE_RE.search(t)
    if m:
        sm, em, year = _month_num(m.group(1)), _month_num(m.group(2)), int(m.group(3))
        if sm and em and year:
            label = _fy_quarter_from_months(sm, em, year)
            if label:
                return _score_candidate(label, 95.0, "month_range")

    m = _SINGLE_MONTH_RE.search(t)
    if m:
        mn, year = _month_num(m.group(1)), int(m.group(2))
        if mn and year:
            label = _fy_quarter_from_months(mn, mn, year)
            if label:
                return _score_candidate(label, 88.0, "single_month")

    parsed_month = parse_month_label(t)
    if parsed_month:
        label = _fy_quarter_from_months(parsed_month[0], parsed_month[0], parsed_month[1])
        if label:
            return _score_candidate(label, 85.0, "month_label")

    return None


def _collect_probe_texts(path: Union[str, Path]) -> List[Tuple[str, str]]:
    """Gather sheet names + early cell text for quarter detection."""
    file_path = Path(path)
    texts: List[Tuple[str, str]] = []
    try:
        for name in list_candidate_sheets(file_path)[:12]:
            texts.append(("sheet_name", name))
            matrix = read_sheet_matrix(file_path, name, max_rows=8, max_cols=12)
            for row in matrix[:6]:
                for cell in row[:10]:
                    if cell is not None and str(cell).strip():
                        texts.append(("cell", str(cell).strip()))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Quarter probe read failed | path={} | err={}", file_path, exc)
    return texts


def detect_reporting_quarter(
    path: Union[str, Path],
    *,
    allow_llm_fallback: bool = True,
    min_confidence: float = 75.0,
) -> Dict[str, Any]:
    """
    Detect reporting quarter from workbook metadata.

    Returns ``{reporting_quarter, confidence, source}`` or empty quarter with low confidence.
    """
    best: Optional[Dict[str, Any]] = None
    for source, text in _collect_probe_texts(path):
        hit = _scan_text(text)
        if not hit:
            continue
        if best is None or hit["confidence"] > best["confidence"]:
            best = {**hit, "matched_text": text[:120], "matched_from": source}

    if best and float(best["confidence"]) >= min_confidence:
        logger.info(
            "Quarter detected | path={} | quarter={} | conf={} | source={}",
            path,
            best["reporting_quarter"],
            best["confidence"],
            best["source"],
        )
        return best

    if allow_llm_fallback:
        llm = _llm_detect_quarter(path)
        if llm and float(llm.get("confidence") or 0) >= min_confidence:
            return llm

    if best:
        return best
    return {"reporting_quarter": None, "confidence": 0.0, "source": "none"}


def _llm_detect_quarter(path: Union[str, Path]) -> Optional[Dict[str, Any]]:
    try:
        from app.database.session import SessionLocal
        from app.services.llm_settings_service import LlmSettingsService, resolve_runtime_llm

        _db = SessionLocal()
        try:
            rt = resolve_runtime_llm(_db)
        finally:
            _db.close()
    except Exception:  # noqa: BLE001
        settings = get_settings()
        rt = {
            "enabled": bool((settings.openai_api_key or "").strip()),
            "api_key": (settings.openai_api_key or "").strip(),
            "model": settings.openai_model or "gpt-4o-mini",
            "timeout": float(settings.openai_timeout_seconds or 60),
        }

    if not rt.get("enabled"):
        return None
    api_key = (rt.get("api_key") or "").strip()
    if not api_key:
        return None

    snippets = [f"{src}: {txt}" for src, txt in _collect_probe_texts(path)[:25]]
    if not snippets:
        return None

    model = rt.get("model") or "gpt-4o-mini"
    body = {
        "model": model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "Detect APCOTEX Indian financial-year reporting quarter from Excel metadata. "
                    "FY Apr-Mar: Q1=Apr-Jun, Q2=Jul-Sep, Q3=Oct-Dec, Q4=Jan-Mar. "
                    "Return JSON only with FY label: "
                    "{\"reporting_quarter\":\"FY 2025-26 • Q2\",\"confidence\":95}"
                ),
            },
            {"role": "user", "content": json.dumps({"snippets": snippets}, ensure_ascii=True)},
        ],
    }
    try:
        with httpx.Client(timeout=float(rt.get("timeout") or 60)) as client:
            resp = client.post(
                OPENAI_CHAT_URL,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=body,
            )
            resp.raise_for_status()
            payload = resp.json()
            content = (
                (((payload.get("choices") or [{}])[0].get("message") or {}).get("content"))
                or ""
            )
        usage = payload.get("usage") if isinstance(payload, dict) else None
        try:
            from app.database.session import SessionLocal
            from app.services.llm_settings_service import LlmSettingsService

            _db = SessionLocal()
            try:
                LlmSettingsService(_db).record_usage(
                    purpose="quarter_detect",
                    usage=usage if isinstance(usage, dict) else {},
                    model=model,
                    provider="openai",
                )
                _db.commit()
            finally:
                _db.close()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to persist LLM usage | purpose=quarter_detect | err={}", exc)

        data = json.loads(content)
        label = str(data.get("reporting_quarter") or "").strip()
        conf = float(data.get("confidence") or 0)
        parsed = parse_quarter_label(label) if label else None
        if parsed and parsed.label:
            return _score_candidate(parsed.label, conf, "llm")
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM quarter detection failed | err={}", exc)
    return None
