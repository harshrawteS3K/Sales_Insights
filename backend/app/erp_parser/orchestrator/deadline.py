"""Stage deadlines so an ingestion always reaches a terminal state."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from typing import Callable, TypeVar

T = TypeVar("T")

# A stage that does not return is abandoned and the request ends as Human Review.
# Ceilings sit above a normal multi-sheet ERP pass so a valid workbook is not
# cut off, and well below an unbounded wait. The structure analyzer stays at 10s.
STAGE_LIMIT_SECONDS = {
    "loader": 45.0,
    "fingerprint": 10.0,
    "classifier": 10.0,
    "scoring": 90.0,
    # LLM stages are not artificially bounded here — Bedrock completes naturally
    # (network-level read ceiling lives in bedrock_client only).
}

HUMAN_REVIEW_TIMEOUT = "Human Review Required\n\nReason : Parser Timeout"


class StageTimeout(Exception):
    def __init__(self, stage: str) -> None:
        self.stage = stage
        super().__init__(HUMAN_REVIEW_TIMEOUT)


def run_bounded(stage: str, fn: Callable[[], T]) -> T:
    """Run one pipeline stage. The caller is not left waiting past the limit."""
    limit = STAGE_LIMIT_SECONDS[stage]
    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"erp-{stage}")
    future = pool.submit(fn)
    try:
        return future.result(timeout=limit)
    except FuturesTimeout as exc:
        raise StageTimeout(stage) from exc
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
