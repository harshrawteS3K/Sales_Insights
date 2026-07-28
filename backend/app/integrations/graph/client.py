"""Reusable Microsoft Graph API client using MSAL client-credentials flow."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import msal
import requests

from app.core.config import settings
from app.core.logging import get_logger
from app.exceptions import GraphAPIError, ValidationAppError

logger = get_logger(__name__)

# Refresh a short time before actual expiry to avoid mid-request failures.
_TOKEN_EXPIRY_SKEW = timedelta(minutes=5)


class GraphClient:
    """
    Production Microsoft Graph client for mailbox operations.

    Authenticates with tenant/client/secret (app-only) and exposes helpers to:
    - list unread messages
    - download Excel attachments
    - mark messages as read
    """

    def __init__(
        self,
        *,
        tenant_id: Optional[str] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        mailbox: Optional[str] = None,
        base_url: Optional[str] = None,
        scope: Optional[str] = None,
    ) -> None:
        self.tenant_id = tenant_id or settings.graph_tenant_id
        self.client_id = client_id or settings.graph_client_id
        self.client_secret = client_secret or settings.graph_client_secret
        self.mailbox = mailbox or settings.graph_mailbox
        self.base_url = (base_url or settings.graph_base_url).rstrip("/")
        self.scope = [scope or settings.graph_scope]
        self._token_cache: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None
        self._app: Optional[msal.ConfidentialClientApplication] = None

    def _validate_config(self) -> None:
        missing = [
            name
            for name, value in {
                "GRAPH_TENANT_ID": self.tenant_id,
                "GRAPH_CLIENT_ID": self.client_id,
                "GRAPH_CLIENT_SECRET": self.client_secret,
            }.items()
            if not value
        ]
        if missing:
            raise GraphAPIError(
                "Microsoft Graph credentials are not configured",
                details={"missing": missing},
            )

    @property
    def msal_app(self) -> msal.ConfidentialClientApplication:
        """Lazy MSAL confidential client."""
        if self._app is None:
            self._validate_config()
            authority = f"{settings.graph_authority_base}/{self.tenant_id}"
            self._app = msal.ConfidentialClientApplication(
                client_id=self.client_id,
                client_credential=self.client_secret,
                authority=authority,
            )
            logger.info("MSAL confidential client initialized for tenant={}", self.tenant_id)
        return self._app

    def _is_token_valid(self) -> bool:
        """Return True when a cached token exists and is not near expiry."""
        if not self._token_cache or self._token_expires_at is None:
            return False
        return datetime.now(timezone.utc) < (self._token_expires_at - _TOKEN_EXPIRY_SKEW)

    @staticmethod
    def _resolve_expiry(result: Dict[str, Any]) -> datetime:
        """Derive token expiry from an MSAL token response."""
        now = datetime.now(timezone.utc)
        expires_on = result.get("expires_on")
        if expires_on is not None:
            try:
                return datetime.fromtimestamp(int(expires_on), tz=timezone.utc)
            except (TypeError, ValueError, OSError):
                logger.warning("Invalid Graph token expires_on={}; falling back to expires_in", expires_on)

        expires_in = result.get("expires_in")
        try:
            seconds = int(expires_in) if expires_in is not None else 3600
        except (TypeError, ValueError):
            seconds = 3600
        return now + timedelta(seconds=max(seconds, 60))

    def acquire_token(self, *, force_refresh: bool = False) -> str:
        """Acquire an application access token for Microsoft Graph."""
        if not force_refresh and self._is_token_valid():
            logger.debug("Reusing cached Microsoft Graph access token")
            return self._token_cache  # type: ignore[return-value]

        logger.info("Acquiring Microsoft Graph access token")
        result = None if force_refresh else self.msal_app.acquire_token_silent(self.scope, account=None)
        if not result:
            result = self.msal_app.acquire_token_for_client(scopes=self.scope)

        if not result or "access_token" not in result:
            error = (result or {}).get("error")
            description = (result or {}).get("error_description")
            logger.error("Failed to acquire Graph token | error={} | desc={}", error, description)
            raise GraphAPIError(
                "Failed to acquire Microsoft Graph access token",
                details={"error": error, "error_description": description},
            )

        self._token_cache = result["access_token"]
        self._token_expires_at = self._resolve_expiry(result)
        logger.info(
            "Microsoft Graph access token acquired successfully | expires_at={}",
            self._token_expires_at.isoformat(),
        )
        return self._token_cache

    def _headers(self) -> Dict[str, str]:
        token = self.acquire_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
        raw: bool = False,
        timeout: int = 60,
    ) -> Any:
        """Execute an authenticated Graph HTTP request."""
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        logger.debug("Graph {} {}", method.upper(), url)
        try:
            response = requests.request(
                method=method.upper(),
                url=url,
                headers=self._headers(),
                params=params,
                json=json_body,
                timeout=timeout,
            )
        except requests.RequestException as exc:
            logger.exception("Graph request failed | url={}", url)
            raise GraphAPIError("Microsoft Graph request failed", details=str(exc)) from exc

        if response.status_code == 401:
            logger.warning("Graph token expired/unauthorized – refreshing and retrying")
            self.acquire_token(force_refresh=True)
            response = requests.request(
                method=method.upper(),
                url=url,
                headers=self._headers(),
                params=params,
                json=json_body,
                timeout=timeout,
            )

        if response.status_code >= 400:
            logger.error(
                "Graph API error | status={} | body={}",
                response.status_code,
                response.text[:1000],
            )
            raise GraphAPIError(
                f"Microsoft Graph API returned HTTP {response.status_code}",
                details=response.text[:2000],
            )

        if raw:
            return response.content
        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    def resolve_mailbox(self, mailbox: Optional[str] = None) -> str:
        """Resolve mailbox address, failing clearly when unset."""
        resolved = (mailbox or self.mailbox or "").strip()
        if not resolved:
            raise ValidationAppError(
                "GRAPH_MAILBOX is not configured. Set it in .env or pass mailbox in the sync request."
            )
        return resolved

    def _user_path(self, mailbox: Optional[str] = None) -> str:
        address = self.resolve_mailbox(mailbox)
        return f"/users/{quote(address)}"

    def list_unread_messages(
        self,
        *,
        mailbox: Optional[str] = None,
        top: int = 50,
        has_attachments: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Return unread messages from the configured mailbox.

        Microsoft Graph requires that when ``$filter`` and ``$orderby`` are used
        together, every ``$orderby`` property also appears in ``$filter`` (and
        before other filter properties). Otherwise Graph returns InefficientFilter.
        """
        user_path = self._user_path(mailbox)
        # receivedDateTime MUST lead $filter when ordering by receivedDateTime.
        filters = ["receivedDateTime ge 1970-01-01T00:00:00Z", "isRead eq false"]
        if has_attachments:
            filters.append("hasAttachments eq true")
        params = {
            "$filter": " and ".join(filters),
            "$top": min(max(top, 1), 200),
            "$orderby": "receivedDateTime desc",
            "$select": (
                "id,subject,receivedDateTime,hasAttachments,isRead,bodyPreview,"
                "conversationId,internetMessageId,from,sender"
            ),
        }
        logger.info(
            "Graph Connected | Listing unread messages | mailbox={} | top={} | filter={}",
            mailbox or self.mailbox,
            top,
            params["$filter"],
        )
        payload = self._request("GET", f"{user_path}/messages", params=params)
        messages = (payload or {}).get("value", [])
        logger.info("Unread Messages Retrieved | count={}", len(messages))
        for msg in messages:
            sender_name, sender_email = self.extract_sender(msg)
            logger.info(
                "Unread message | id={} | subject={} | sender={} <{}> | received={} | hasAttachments={} | internetMessageId={}",
                msg.get("id"),
                msg.get("subject"),
                sender_name,
                sender_email,
                msg.get("receivedDateTime"),
                msg.get("hasAttachments"),
                msg.get("internetMessageId"),
            )
        return messages

    def list_attachments(self, message_id: str, *, mailbox: Optional[str] = None) -> List[Dict[str, Any]]:
        """List attachments for a message.

        Note: ``@odata.type`` must NOT appear in ``$select`` — Graph rejects it
        with HTTP 400. The type is still returned in the default payload.
        """
        user_path = self._user_path(mailbox)
        logger.info("Attachment List | message_id={}", message_id)
        payload = self._request(
            "GET",
            f"{user_path}/messages/{quote(message_id)}/attachments",
            params={
                "$select": "id,name,contentType,size,isInline",
            },
        )
        attachments = (payload or {}).get("value", [])
        logger.info("Attachment List complete | message_id={} | count={}", message_id, len(attachments))
        return attachments

    def download_attachment(
        self,
        message_id: str,
        attachment_id: str,
        *,
        mailbox: Optional[str] = None,
    ) -> bytes:
        """Download attachment content bytes."""
        user_path = self._user_path(mailbox)
        # Prefer $value for file attachments; fall back to contentBytes in JSON.
        try:
            content = self._request(
                "GET",
                f"{user_path}/messages/{quote(message_id)}/attachments/{quote(attachment_id)}/$value",
                raw=True,
            )
            if isinstance(content, (bytes, bytearray)) and content:
                return bytes(content)
        except GraphAPIError:
            logger.debug("Attachment $value failed; falling back to contentBytes JSON")

        payload = self._request(
            "GET",
            f"{user_path}/messages/{quote(message_id)}/attachments/{quote(attachment_id)}",
        )
        import base64

        encoded = (payload or {}).get("contentBytes")
        if not encoded:
            raise GraphAPIError("Attachment content is empty")
        return base64.b64decode(encoded)

    def mark_as_read(self, message_id: str, *, mailbox: Optional[str] = None) -> None:
        """Mark a message as read after successful processing."""
        user_path = self._user_path(mailbox)
        logger.info("Marking Graph message as read | message_id={}", message_id)
        self._request(
            "PATCH",
            f"{user_path}/messages/{quote(message_id)}",
            json_body={"isRead": True},
        )

    @staticmethod
    def is_excel_attachment(attachment: Dict[str, Any]) -> bool:
        """Return True when attachment looks like an Excel file."""
        name = (attachment.get("name") or "").lower()
        content_type = (attachment.get("contentType") or "").lower()
        extension = Path(name).suffix.lower()
        if extension in {ext.lower() for ext in settings.graph_excel_extensions}:
            return True
        excel_types = {
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.ms-excel.sheet.macroenabled.12",
            "application/vnd.ms-excel",
            "application/excel",
        }
        return content_type in excel_types or extension == ".xls"

    @staticmethod
    def extract_sender(message: Dict[str, Any]) -> tuple[str, str]:
        """Extract (sender_name, sender_email) from a Graph message payload."""
        sender = message.get("from") or message.get("sender") or {}
        email_addr = sender.get("emailAddress") or {}
        name = email_addr.get("name") or ""
        address = (email_addr.get("address") or "").lower()
        return name, address
