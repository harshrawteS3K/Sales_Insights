"""Outlook-ready .eml draft + ZIP package for quarterly distributor templates."""

from __future__ import annotations

import io
import re
import zipfile
from email import policy
from email.message import EmailMessage
from pathlib import Path
from typing import Optional, Tuple

from app.core.logging import get_logger
from app.utils.files import ensure_dir

logger = get_logger(__name__)

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def sanitize_filename_part(value: str) -> str:
    cleaned = _SAFE.sub("_", (value or "").strip()).strip("._")
    return cleaned or "Distributor"


class EmailPackageService:
    """Build .eml drafts with Excel attachment and ZIP them for download."""

    def build_eml_bytes(
        self,
        *,
        to_email: str,
        cc_email: Optional[str],
        contact_person: str,
        reporting_quarter: str,
        excel_path: Path,
        excel_filename: str,
    ) -> bytes:
        """Return RFC822 .eml bytes with prefilled To/CC/Subject/Body + attachment."""
        msg = EmailMessage(policy=policy.SMTP)
        msg["To"] = to_email
        if cc_email:
            msg["Cc"] = cc_email
        msg["Subject"] = f"APCOTEX Quarterly Sales Template – {reporting_quarter}"
        msg["X-Unsent"] = "1"  # Outlook opens as editable draft

        greeting = (contact_person or "Partner").strip() or "Partner"
        body = (
            f"Dear {greeting},\n\n"
            f"Please find attached the APCOTEX Quarterly Sales Template for {reporting_quarter}.\n\n"
            "Kindly fill in the sales quantity details for your mapped customers and "
            "share the completed file by replying to this email.\n\n"
            "Quarter Mapping:\n"
            "Q1 = Apr–Jun\n"
            "Q2 = Jul–Sep\n"
            "Q3 = Oct–Dec\n"
            "Q4 = Jan–Mar\n\n"
            "Regards,\n"
            "APCOTEX Team\n"
        )
        msg.set_content(body)

        excel_bytes = Path(excel_path).read_bytes()
        msg.add_attachment(
            excel_bytes,
            maintype="application",
            subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=excel_filename,
        )
        return msg.as_bytes(policy=policy.SMTP)

    def build_zip_bytes(
        self,
        *,
        excel_path: Path,
        excel_filename: str,
        eml_bytes: bytes,
        eml_filename: str,
    ) -> bytes:
        """ZIP containing the Excel template and Outlook draft."""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.write(excel_path, arcname=excel_filename)
            zf.writestr(eml_filename, eml_bytes)
        return buffer.getvalue()

    def package_filenames(
        self, *, company_or_name: str, reporting_quarter: str
    ) -> Tuple[str, str, str]:
        """Return (stem, xlsx_name, eml_name)."""
        stem = (
            f"Apcotex_{sanitize_filename_part(company_or_name)}_"
            f"{sanitize_filename_part(reporting_quarter)}"
        )
        return stem, f"{stem}.xlsx", f"{stem}.eml"

    def write_package(
        self,
        *,
        output_dir: Path,
        company_or_name: str,
        reporting_quarter: str,
        to_email: str,
        cc_email: Optional[str],
        contact_person: str,
        excel_path: Path,
    ) -> Tuple[Path, str]:
        """
        Write ZIP to disk. Returns (zip_path, zip_filename).
        """
        ensure_dir(output_dir)
        stem, xlsx_name, eml_name = self.package_filenames(
            company_or_name=company_or_name, reporting_quarter=reporting_quarter
        )
        # Copy/rename excel into package naming if needed
        packaged_excel = output_dir / xlsx_name
        if Path(excel_path).resolve() != packaged_excel.resolve():
            packaged_excel.write_bytes(Path(excel_path).read_bytes())

        eml_bytes = self.build_eml_bytes(
            to_email=to_email,
            cc_email=cc_email,
            contact_person=contact_person,
            reporting_quarter=reporting_quarter,
            excel_path=packaged_excel,
            excel_filename=xlsx_name,
        )
        zip_name = f"{stem}.zip"
        zip_path = output_dir / zip_name
        zip_path.write_bytes(
            self.build_zip_bytes(
                excel_path=packaged_excel,
                excel_filename=xlsx_name,
                eml_bytes=eml_bytes,
                eml_filename=eml_name,
            )
        )
        logger.info(
            "Quarterly package written | zip={} | excel={} | eml={}",
            zip_path.name,
            xlsx_name,
            eml_name,
        )
        return zip_path, zip_name
