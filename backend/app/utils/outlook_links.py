"""Outlook deep-link helpers (no hardcoded mailbox URLs beyond Graph webLink)."""

from typing import Optional
from urllib.parse import quote


def outlook_deeplink_from_graph_id(graph_message_id: str) -> str:
    """
    Build an Outlook on the web deep link from a Graph message id.

    Prefer the Graph ``webLink`` property when available; this is a fallback only.
    """
    encoded = quote(graph_message_id, safe="")
    return (
        "https://outlook.office.com/mail/deeplink/read/"
        f"{encoded}?ItemID={encoded}&exvsurl=1"
    )


def resolve_outlook_open_url(
    *,
    web_link: Optional[str],
    graph_message_id: Optional[str],
) -> Optional[str]:
    """Return the best URL to open the original Outlook message, or None."""
    link = (web_link or "").strip()
    if link.startswith("http://") or link.startswith("https://"):
        return link
    gid = (graph_message_id or "").strip()
    if gid:
        return outlook_deeplink_from_graph_id(gid)
    return None
