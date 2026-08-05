"""Customer Master parse result with explicit skip accounting."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class CustomerMasterParseResult:
    """
    Parse outcome for Customer Master replace.

    Every Excel data row is classified: imported, blank name, duplicate, or validation error.
    No silent skips.
    """

    records: List[Dict[str, str]] = field(default_factory=list)
    excel_rows: int = 0
    blank_customer_name: int = 0
    duplicate_names: int = 0
    validation_errors: int = 0

    @property
    def imported(self) -> int:
        return len(self.records)

    @property
    def skipped(self) -> int:
        return self.blank_customer_name + self.duplicate_names + self.validation_errors

    def summary_message(self) -> str:
        """Human-readable replace summary for API / UI."""
        return (
            "Customer Master Replace Complete\n"
            f"Excel Rows          : {self.excel_rows}\n"
            f"Imported            : {self.imported}\n"
            f"Duplicate Names     : {self.duplicate_names}\n"
            f"Blank Customer Name : {self.blank_customer_name}\n"
            f"Validation Errors   : {self.validation_errors}\n"
            f"Skipped             : {self.skipped}"
        )
