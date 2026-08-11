"""Bulk Outlook draft creation — sequential orchestration + partial success."""

from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from openpyxl import load_workbook
from sqlalchemy.orm import Session

from app.database.session import SessionLocal
from app.exceptions import GraphAPIError, ValidationAppError
from app.integrations.graph.client import GraphClient
from app.repositories.distributor_repository import DistributorRepository
from app.services import bulk_email_draft_service as bulk_svc
from app.services.report_service import ReportService
from app.services.template_generation_service import TemplateGenerationService
from tests.workbook_helpers import build_official_workbook


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
        session.rollback()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@pytest.fixture(autouse=True)
def _reset_bulk_jobs():
    bulk_svc.reset_jobs_for_tests()
    yield
    bulk_svc.reset_jobs_for_tests()


def _uid(prefix: str) -> str:
    return f"{prefix} {uuid4().hex[:8]}"


def _seed_products(db: Session) -> None:
    from app.models.product_master import ProductMaster
    from app.repositories.master_repository import ProductMasterRepository

    if ProductMasterRepository(db).list_codes_by_segment():
        return
    for industry, code in [("Paper", "P1"), ("Paper", "P2"), ("Carpet", "C1")]:
        db.add(
            ProductMaster(
                industry_type=industry,
                product_code=code,
                is_active=True,
            )
        )
    db.flush()


def _seed_distributor(
    db: Session,
    tmp_path: Path,
    *,
    company: str,
    customer: str,
    email: str | None,
    quarter: str = "Q1 2095",
) -> int:
    path = build_official_workbook(
        tmp_path / f"{company.replace(' ', '_')}.xlsx",
        distributor="Rep",
        company=company,
        reporting_month=quarter,
        rows=[(1, customer, "Paper", "P1", 10)],
    )
    ReportService(db).ingest_excel(path, actor="tester")
    dist = DistributorRepository(db).get_by_company(company)
    assert dist is not None
    if email:
        # Unique active-email index — suffix with company token
        local, _, domain = email.partition("@")
        token = uuid4().hex[:8]
        dist.email = f"{local}+{token}@{domain}" if domain else f"{email}+{token}"
    else:
        dist.email = None
    dist.contact_person = "Contact"
    db.flush()
    return int(dist.id)


def _wait_job(job_id: str, timeout_s: float = 30.0):
    import time

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        job = bulk_svc.get_job(job_id)
        assert job is not None
        if job.status in {"completed", "failed"}:
            return job
        time.sleep(0.05)
    raise AssertionError(f"Job {job_id} did not finish within {timeout_s}s")


def test_bulk_all_three_succeed(db: Session, tmp_path: Path, monkeypatch):
    _seed_products(db)
    ids = []
    for i, cust in enumerate(["CustA", "CustB", "CustC"]):
        ids.append(
            _seed_distributor(
                db,
                tmp_path,
                company=_uid(f"BulkOK{i}"),
                customer=cust,
                email=f"ok{i}@example.com",
            )
        )
    db.commit()

    attachments: list[tuple[str, bytes]] = []
    recipients: list[str] = []

    def create_draft(*, subject, body_text, to_email, cc_email=None, mailbox=None):
        recipients.append(to_email)
        return {"id": f"draft-{to_email}"}

    def add_att(draft_id, filename=None, content=None, mailbox=None, **_):
        attachments.append((filename or "", content or b""))
        return {"id": "att"}

    mock_graph = MagicMock(spec=GraphClient)
    mock_graph.resolve_mailbox.return_value = "salesinsights@apcotex.com"
    mock_graph.create_draft_message.side_effect = create_draft
    mock_graph.add_file_attachment.side_effect = add_att

    orig_init = TemplateGenerationService.__init__

    def patched_init(self, session):
        orig_init(self, session)
        self.graph = mock_graph

    monkeypatch.setattr(TemplateGenerationService, "__init__", patched_init)

    job = bulk_svc.start_bulk_email_drafts(
        distributor_ids=ids,
        reporting_quarter="Q3 2095",
        actor="admin",
    )
    done = _wait_job(job.job_id)
    assert done.status == "completed"
    assert done.total == 3
    assert done.successful == 3
    assert done.failed == 0
    assert len(recipients) == 3
    assert len(attachments) == 3
    assert len({a[0] for a in attachments}) == 3  # unique filenames
    for _, content in attachments:
        assert content[:2] == b"PK"
        # load from bytes via temp — openpyxl needs path; use attachment names on disk
    assert "sendMail" not in str(mock_graph.method_calls).lower()


def test_bulk_partial_missing_email(db: Session, tmp_path: Path, monkeypatch):
    _seed_products(db)
    ok1 = _seed_distributor(
        db, tmp_path, company=_uid("PartialA"), customer="CA", email="a@example.com"
    )
    bad = _seed_distributor(
        db, tmp_path, company=_uid("PartialBad"), customer="CB", email=None
    )
    ok2 = _seed_distributor(
        db, tmp_path, company=_uid("PartialC"), customer="CC", email="c@example.com"
    )
    db.commit()

    mock_graph = MagicMock(spec=GraphClient)
    mock_graph.resolve_mailbox.return_value = "salesinsights@apcotex.com"
    mock_graph.create_draft_message.return_value = {"id": "d1"}
    mock_graph.add_file_attachment.return_value = {"id": "a1"}

    orig_init = TemplateGenerationService.__init__

    def patched_init(self, session):
        orig_init(self, session)
        self.graph = mock_graph

    monkeypatch.setattr(TemplateGenerationService, "__init__", patched_init)

    job = bulk_svc.start_bulk_email_drafts(
        distributor_ids=[ok1, bad, ok2],
        reporting_quarter="Q3 2095",
        actor="admin",
    )
    done = _wait_job(job.job_id)
    assert done.successful == 2
    assert done.failed == 1
    fail = next(r for r in done.results if not r.success)
    assert fail.distributor_id == bad
    assert "email" in (fail.reason or "").lower()
    # Successful drafts not rolled back — Graph called twice
    assert mock_graph.create_draft_message.call_count == 2


def test_bulk_graph_failure_continues(db: Session, tmp_path: Path, monkeypatch):
    _seed_products(db)
    id1 = _seed_distributor(
        db, tmp_path, company=_uid("GFail1"), customer="C1", email="1@example.com"
    )
    id2 = _seed_distributor(
        db, tmp_path, company=_uid("GFail2"), customer="C2", email="2@example.com"
    )
    id3 = _seed_distributor(
        db, tmp_path, company=_uid("GFail3"), customer="C3", email="3@example.com"
    )
    db.commit()

    call_n = {"n": 0}

    def create_draft(**kwargs):
        call_n["n"] += 1
        if call_n["n"] == 2:
            raise GraphAPIError("Microsoft Graph API returned HTTP 500", details="boom")
        return {"id": f"d-{call_n['n']}"}

    mock_graph = MagicMock(spec=GraphClient)
    mock_graph.resolve_mailbox.return_value = "salesinsights@apcotex.com"
    mock_graph.create_draft_message.side_effect = create_draft
    mock_graph.add_file_attachment.return_value = {"id": "a"}

    orig_init = TemplateGenerationService.__init__

    def patched_init(self, session):
        orig_init(self, session)
        self.graph = mock_graph

    monkeypatch.setattr(TemplateGenerationService, "__init__", patched_init)

    job = bulk_svc.start_bulk_email_drafts(
        distributor_ids=[id1, id2, id3],
        reporting_quarter="Q3 2095",
        actor="admin",
    )
    done = _wait_job(job.job_id)
    assert done.successful == 2
    assert done.failed == 1
    fail = next(r for r in done.results if not r.success)
    assert fail.distributor_id == id2
    assert "Unable to create Outlook draft" in (fail.reason or "")


def test_bulk_duplicate_submission_blocked(db: Session, tmp_path: Path, monkeypatch):
    _seed_products(db)
    ids = [
        _seed_distributor(
            db, tmp_path, company=_uid("Dup"), customer="C", email="d@example.com"
        )
    ]
    db.commit()

    import time

    mock_graph = MagicMock(spec=GraphClient)
    mock_graph.resolve_mailbox.return_value = "salesinsights@apcotex.com"

    def slow_draft(**_):
        time.sleep(0.4)
        return {"id": "slow"}

    mock_graph.create_draft_message.side_effect = slow_draft
    mock_graph.add_file_attachment.return_value = {"id": "a"}

    orig_init = TemplateGenerationService.__init__

    def patched_init(self, session):
        orig_init(self, session)
        self.graph = mock_graph

    monkeypatch.setattr(TemplateGenerationService, "__init__", patched_init)

    job1 = bulk_svc.start_bulk_email_drafts(
        distributor_ids=ids, reporting_quarter="Q3 2095", actor="admin"
    )
    with pytest.raises(ValidationAppError) as exc:
        bulk_svc.start_bulk_email_drafts(
            distributor_ids=ids, reporting_quarter="Q3 2095", actor="admin"
        )
    assert "already running" in str(exc.value.message).lower()
    _wait_job(job1.job_id)


def test_bulk_retry_failed_only(db: Session, tmp_path: Path, monkeypatch):
    _seed_products(db)
    ok = _seed_distributor(
        db, tmp_path, company=_uid("RetryOK"), customer="C1", email="ok@example.com"
    )
    bad = _seed_distributor(
        db, tmp_path, company=_uid("RetryBad"), customer="C2", email=None
    )
    db.commit()

    mock_graph = MagicMock(spec=GraphClient)
    mock_graph.resolve_mailbox.return_value = "salesinsights@apcotex.com"
    mock_graph.create_draft_message.return_value = {"id": "d"}
    mock_graph.add_file_attachment.return_value = {"id": "a"}

    orig_init = TemplateGenerationService.__init__

    def patched_init(self, session):
        orig_init(self, session)
        self.graph = mock_graph

    monkeypatch.setattr(TemplateGenerationService, "__init__", patched_init)

    job = bulk_svc.start_bulk_email_drafts(
        distributor_ids=[ok, bad], reporting_quarter="Q3 2095", actor="admin"
    )
    done = _wait_job(job.job_id)
    assert done.failed == 1
    failed_ids = [r.distributor_id for r in done.results if not r.success]
    assert failed_ids == [bad]

    # Fix email and retry only failed
    dist = DistributorRepository(db).get_by_id(bad)
    assert dist is not None
    dist.email = f"fixed+{uuid4().hex[:8]}@example.com"
    db.commit()

    job2 = bulk_svc.start_bulk_email_drafts(
        distributor_ids=failed_ids, reporting_quarter="Q3 2095", actor="admin"
    )
    done2 = _wait_job(job2.job_id)
    assert done2.total == 1
    assert done2.successful == 1
    assert done2.failed == 0


def test_bulk_correct_recipient_and_attachment_per_distributor(
    db: Session, tmp_path: Path, monkeypatch
):
    _seed_products(db)
    c1 = _uid("AttachA")
    c2 = _uid("AttachB")
    id1 = _seed_distributor(
        db, tmp_path, company=c1, customer="OnlyA", email="a@example.com"
    )
    id2 = _seed_distributor(
        db, tmp_path, company=c2, customer="OnlyB", email="b@example.com"
    )
    db.commit()

    seen = []

    def create_draft(*, subject, body_text, to_email, cc_email=None, mailbox=None):
        return {"id": f"draft-{to_email}"}

    def add_att(draft_id, filename=None, content=None, mailbox=None, **_):
        seen.append({"draft_id": draft_id, "filename": filename, "content": content})
        return {"id": "att"}

    mock_graph = MagicMock(spec=GraphClient)
    mock_graph.resolve_mailbox.return_value = "salesinsights@apcotex.com"
    mock_graph.create_draft_message.side_effect = create_draft
    mock_graph.add_file_attachment.side_effect = add_att

    orig_init = TemplateGenerationService.__init__

    def patched_init(self, session):
        orig_init(self, session)
        self.graph = mock_graph

    monkeypatch.setattr(TemplateGenerationService, "__init__", patched_init)

    job = bulk_svc.start_bulk_email_drafts(
        distributor_ids=[id1, id2], reporting_quarter="Q3 2095", actor="admin"
    )
    done = _wait_job(job.job_id)
    assert done.successful == 2
    assert seen[0]["draft_id"].startswith("draft-")
    assert seen[1]["draft_id"].startswith("draft-")
    assert seen[0]["draft_id"] != seen[1]["draft_id"]
    assert seen[0]["filename"] != seen[1]["filename"]
    assert "a+" in seen[0]["draft_id"] or "a@" in seen[0]["draft_id"]
    assert "b+" in seen[1]["draft_id"] or "b@" in seen[1]["draft_id"]

    # Customer dropdowns are distributor-specific
    from app.core.config import settings

    packages = Path(settings.download_dir) / "packages"
    for item, expected_customer in zip(seen, ["OnlyA", "OnlyB"]):
        matches = list(packages.glob(item["filename"]))
        assert matches, item["filename"]
        wb = load_workbook(matches[0], data_only=True)
        lists = wb["_lists"] if "_lists" in wb.sheetnames else None
        assert lists is not None
        names = [
            str(lists.cell(r, 1).value).strip()
            for r in range(1, 50)
            if lists.cell(r, 1).value
        ]
        assert expected_customer in names
        wb.close()


def test_graph_429_retries_then_succeeds(monkeypatch):
    """Bounded 429 handling in GraphClient._request."""
    client = GraphClient(
        tenant_id="t",
        client_id="c",
        client_secret="s",
        mailbox="salesinsights@apcotex.com",
    )
    client._headers = lambda: {"Authorization": "Bearer tok"}  # type: ignore[method-assign]

    calls = {"n": 0}

    class FakeResp:
        def __init__(self, status, payload=None, headers=None):
            self.status_code = status
            self.headers = headers or {}
            self._payload = payload or {}
            self.content = b'{"id":"ok"}' if status == 200 else b"throttled"
            self.text = self.content.decode()

        def json(self):
            return self._payload

    def fake_request(**kwargs):
        calls["n"] += 1
        if calls["n"] < 3:
            return FakeResp(429, headers={"Retry-After": "0"})
        return FakeResp(200, payload={"id": "ok"})

    monkeypatch.setattr("app.integrations.graph.client.requests.request", fake_request)
    monkeypatch.setattr("app.integrations.graph.client.time.sleep", lambda *_: None)

    out = client._request("GET", "/me")
    assert out == {"id": "ok"}
    assert calls["n"] == 3


def test_single_create_email_draft_still_works(db: Session, tmp_path: Path, monkeypatch):
    _seed_products(db)
    company = _uid("SingleStill")
    dist_id = _seed_distributor(
        db, tmp_path, company=company, customer="Solo", email="solo@example.com"
    )
    db.commit()

    mock_graph = MagicMock(spec=GraphClient)
    mock_graph.resolve_mailbox.return_value = "salesinsights@apcotex.com"
    mock_graph.create_draft_message.return_value = {"id": "single"}
    mock_graph.add_file_attachment.return_value = {"id": "a"}

    svc = TemplateGenerationService(db)
    svc.graph = mock_graph
    result = svc.create_email_draft(
        distributor_id=dist_id, reporting_quarter="Q3 2095", actor="admin"
    )
    assert result.success is True
    assert result.draft_id == "single"
    assert "sendMail" not in str(mock_graph.method_calls).lower()
