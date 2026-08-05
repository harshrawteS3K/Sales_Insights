"""Password hashing and policy helpers (bcrypt)."""

from __future__ import annotations

import re
from typing import Optional, Tuple

import bcrypt

from app.core.config import settings
from app.exceptions import ValidationAppError

_SPECIAL = re.compile(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>/?`~]")


def hash_password(plain: str) -> str:
    """Return a bcrypt hash for storage. Never store plaintext."""
    raw = plain.encode("utf-8")
    if len(raw) > 72:
        raw = raw[:72]
    return bcrypt.hashpw(raw, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: Optional[str]) -> bool:
    """Constant-time verify against a stored bcrypt hash."""
    if not hashed:
        return False
    try:
        raw = plain.encode("utf-8")
        if len(raw) > 72:
            raw = raw[:72]
        return bcrypt.checkpw(raw, hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def validate_password_strength(password: str) -> None:
    """
    Enforce strong password policy.

    - Minimum length (configurable)
    - At least one uppercase, one lowercase, one digit, one special character
    """
    min_len = settings.password_min_length
    if not password or len(password) < min_len:
        raise ValidationAppError(f"Password must be at least {min_len} characters")
    if not re.search(r"[A-Z]", password):
        raise ValidationAppError("Password must include at least one uppercase letter")
    if not re.search(r"[a-z]", password):
        raise ValidationAppError("Password must include at least one lowercase letter")
    if not re.search(r"\d", password):
        raise ValidationAppError("Password must include at least one digit")
    if not _SPECIAL.search(password):
        raise ValidationAppError("Password must include at least one special character")


def validate_password_pair(new_password: str, confirm_password: str) -> None:
    """Validate strength and that confirmation matches."""
    if new_password != confirm_password:
        raise ValidationAppError("Passwords do not match")
    validate_password_strength(new_password)


def normalize_username(username: str) -> str:
    """Normalize login username for storage and lookup."""
    return (username or "").strip().lower()


def is_valid_username(username: str) -> Tuple[bool, str]:
    """Basic username format check."""
    value = normalize_username(username)
    if len(value) < 3:
        return False, "Username must be at least 3 characters"
    if len(value) > 100:
        return False, "Username must be at most 100 characters"
    if not re.fullmatch(r"[a-z0-9._\-]+", value):
        return False, "Username may only contain letters, digits, dots, underscores, and hyphens"
    return True, value
