"""Excel validation helpers for master data uploads."""

from pathlib import Path
from typing import Union

from app.exceptions import ExcelProcessingError, ValidationAppError
from app.integrations.excel.parser import ExcelParserService
from app.integrations.excel.product_master_parser import (
    ProductMasterParseResult,
    parse_product_master_workbook,
)
from app.utils.files import validate_excel_filename
from app.validators.excel_validators import validate_customer_master_dataframe


class ExcelValidationService:
    """Validate Excel uploads before master-data import."""

    def __init__(self, parser: ExcelParserService | None = None) -> None:
        self.parser = parser or ExcelParserService()

    def assert_excel_file(self, filename: str | None) -> None:
        """Reject non-Excel uploads."""
        try:
            validate_excel_filename(filename or "")
        except ValidationAppError as exc:
            raise ExcelProcessingError(str(exc)) from exc

    def validate_customer_master_file(self, path: Union[str, Path]) -> None:
        """Ensure Customer Master has CUSTOMER NAME (fail before any DB write)."""
        df = self.parser.read_dataframe(path)
        validate_customer_master_dataframe(df)

    def validate_product_master_file(self, path: Union[str, Path]) -> ProductMasterParseResult:
        """
        Parse + validate Product Master in one pass (multi-block aware).

        Returns the parse result so callers do not need to parse again.
        """
        return parse_product_master_workbook(path)
