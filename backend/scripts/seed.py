"""UAT seed — Persona Management master data (idempotent).

Usage (from repo root or backend/):
    python backend/scripts/seed.py
    python scripts/seed.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.constants.business_segments import BUSINESS_SEGMENTS
from app.database.session import SessionLocal
from app.enums import OutlookSyncPermission, UserRole
from app.models.distributor import Distributor
from app.models.user import User
from app.models.user_distributor import UserDistributor
from app.models.user_segment import UserSegment
from app.utils.distributor_name import normalize_company_name
from app.utils.passwords import hash_password, normalize_username

DEFAULT_PASSWORD = "Sales@123"

# Seed aliases → values stored on users.outlook_sync_permission
_SYNC_ALIAS_TO_MODEL = {
    "no_sync": OutlookSyncPermission.NONE.value,
    "own_sync": OutlookSyncPermission.OWN.value,
    "all_sync": OutlookSyncPermission.ALL.value,
    OutlookSyncPermission.NONE.value: OutlookSyncPermission.NONE.value,
    OutlookSyncPermission.OWN.value: OutlookSyncPermission.OWN.value,
    OutlookSyncPermission.ALL.value: OutlookSyncPermission.ALL.value,
}

# ---------------------------------------------------------------------------
# Persona Management master (email = unique key)
# ---------------------------------------------------------------------------

PERSONA_SEED: List[Dict[str, Any]] = [
    {
        "full_name": "Mr. Debrabata",
        "email": "debabrata@apcotex.com",
        "username": "admin",
        "role": UserRole.ADMIN.value,
        "title": "Admin",
        "is_active": True,
        "sync_outlook": "all_sync",
        "segments": [],
        "distributors": [
            "REDACHEM VIETNAM COMPANY LIMITED",
        ],
    },
    {
        "full_name": "Ashok Kumar Karuneegar",
        "email": "ashok.karuneegar@apcotex.com",
        "username": "ashok",
        "role": UserRole.USER.value,
        "title": "Sales Owner",
        "is_active": True,
        "sync_outlook": "own_sync",
        "segments": ["Rubber"],
        "distributors": [
            "Ceyenar Chemicals Pvt. Ltd",
            "South India Rubber & Chemicals",
        ],
    },
    {
        "full_name": "Jaideep Tewani",
        "email": "jgtewani@apcotex.com",
        "username": "jaideep",
        "role": UserRole.USER.value,
        "title": "Sales Owner",
        "is_active": True,
        "sync_outlook": "own_sync",
        "segments": ["Construction"],
        "distributors": [
            "ALTEK INTERNATIONAL FZE",
            "Reda Industrial Materials FZE",
        ],
    },
    {
        "full_name": "Jitender Bhatia",
        "email": "jitender.bhatia@apcotex.com",
        "username": "jitender",
        "role": UserRole.USER.value,
        "title": "Sales Owner",
        "is_active": True,
        "sync_outlook": "own_sync",
        "segments": ["Rubber"],
        "distributors": [
            "Arien Impex Private Limited",
            "BPS INTERNATIONAL PVT. LTD.",
            "Chowdhry Rubber Co. Pvt. Ltd.",
            "D. S. Polymers",
            "Kemco Agencies",
            "Kirpa Ram Ramji Das",
            "S.K. TRADING CO.",
        ],
    },
    {
        "full_name": "Maruti Babar",
        "email": "msbabar@apcotex.com",
        "username": "maruti",
        "role": UserRole.USER.value,
        "title": "Sales Owner",
        "is_active": True,
        "sync_outlook": "own_sync",
        "segments": ["Rubber"],
        "distributors": [
            "Chhabra Rubber Trading Co",
            "Goel Mineral & Chemicals",
            "Kohinoor Tyres Pvt. Ltd",
            "Purandar Investment Pvt Ltd",
        ],
    },
    {
        "full_name": "Nilesh Sawant",
        "email": "nilesh.sawant@apcotex.com",
        "username": "nilesh",
        "role": UserRole.USER.value,
        "title": "Sales Owner",
        "is_active": True,
        "sync_outlook": "own_sync",
        "segments": ["Carpet"],
        "distributors": [
            "Puneet Dyes & Chemicals Co.",
        ],
    },
    {
        "full_name": "Prasanta Mohanty",
        "email": "prasanta.mohanty@apcotex.com",
        "username": "prasanta",
        "role": UserRole.USER.value,
        "title": "Sales Owner",
        "is_active": True,
        "sync_outlook": "own_sync",
        "segments": ["Paper"],
        "distributors": [
            "Banmark LLC",
            "Bansal Dye Chem Pvt. Ltd",
            "Damodardas Haridas Private Limited",
        ],
    },
    {
        "full_name": "Prince Singh",
        "email": "princek.singh@apcotex.com",
        "username": "prince",
        "role": UserRole.USER.value,
        "title": "Sales Owner",
        "is_active": True,
        "sync_outlook": "own_sync",
        "segments": ["Rubber"],
        "distributors": [
            "A.B. BROTHERS",
            "Avik Polychem",
            "B.P. CHEMICALS",
        ],
    },
    {
        "full_name": "Rushikesh Kadam",
        "email": "rushikesh.kadam@apcotex.com",
        "username": "rushikesh",
        "role": UserRole.USER.value,
        "title": "Sales Owner",
        "is_active": True,
        "sync_outlook": "own_sync",
        "segments": ["Construction"],
        "distributors": [
            "ASSOCIATED DYECHEM CORPORATION",
            "Badamikar & Co",
            "Classic Solvents Pvt. Ltd",
            "Coat & Crete Speciality Products",
            "Kalpana Polymers Pvt. Ltd",
            "Kapadia Enterprises",
            "Meet Marketing (I) Pvt. Ltd",
            "Pavan Associates",
            "Shri Sai & Company",
            "Sunadz Technology",
        ],
    },
    {
        "full_name": "Sachin Kasar",
        "email": "sachin.kasar@apcotex.com",
        "username": "sachin",
        "role": UserRole.USER.value,
        "title": "Sales Owner",
        "is_active": True,
        "sync_outlook": "own_sync",
        "segments": ["Gloves"],
        "distributors": [
            "BEHN MEYER SPECIALTIES (M) PLT",
            "Behn Meyer Vietnam",
            "Uni Film Co. Ltd",
        ],
    },
]


def _norm_email(email: str) -> str:
    return (email or "").strip().lower()


def _resolve_sync_permission(raw: str, *, role: str) -> str:
    key = (raw or "").strip().lower()
    if key in _SYNC_ALIAS_TO_MODEL:
        return _SYNC_ALIAS_TO_MODEL[key]
    if role in {UserRole.ADMIN.value, UserRole.SUPER_ADMIN.value}:
        return OutlookSyncPermission.ALL.value
    return OutlookSyncPermission.OWN.value


def _get_user_by_email(db: Session, email: str) -> Optional[User]:
    return db.scalar(
        select(User).where(
            func.lower(User.email) == _norm_email(email),
            User.is_deleted.is_(False),
        )
    )


def _username_taken(db: Session, username: str, *, exclude_user_id: Optional[int] = None) -> bool:
    uname = normalize_username(username)
    stmt = select(User.id).where(
        func.lower(User.username) == uname,
        User.is_deleted.is_(False),
    )
    if exclude_user_id is not None:
        stmt = stmt.where(User.id != exclude_user_id)
    return db.scalar(stmt) is not None


def _ensure_username(db: Session, preferred: str, email: str, *, exclude_user_id: Optional[int] = None) -> str:
    base = normalize_username(preferred) or normalize_username(_norm_email(email).split("@")[0])
    if not base:
        base = "user"
    candidate = base
    n = 2
    while _username_taken(db, candidate, exclude_user_id=exclude_user_id):
        candidate = f"{base}{n}"
        n += 1
    return candidate


def upsert_user(db: Session, persona: Dict[str, Any], counters: Dict[str, int]) -> User:
    email = _norm_email(persona["email"])
    role = persona["role"]
    sync_perm = _resolve_sync_permission(str(persona.get("sync_outlook") or ""), role=role)
    full_name = (persona.get("full_name") or "").strip()
    title = (persona.get("title") or ("Admin" if role == UserRole.ADMIN.value else "Sales Owner")).strip()
    is_active = bool(persona.get("is_active", True))
    preferred_username = str(persona.get("username") or email.split("@")[0])

    user = _get_user_by_email(db, email)
    if user is None:
        username = _ensure_username(db, preferred_username, email)
        user = User(
            username=username,
            email=email,
            full_name=full_name,
            title=title,
            password_hash=hash_password(DEFAULT_PASSWORD),
            role=role,
            is_active=is_active,
            is_deleted=False,
            outlook_sync_permission=sync_perm,
        )
        db.add(user)
        db.flush()
        counters["users_created"] += 1
        counters["permissions_updated"] += 1
        return user

    changed = False
    if (user.full_name or "") != full_name:
        user.full_name = full_name
        changed = True
    if (user.role or "") != role:
        user.role = role
        changed = True
    if (user.title or "") != title:
        user.title = title
        changed = True
    if bool(user.is_active) != is_active:
        user.is_active = is_active
        changed = True
    if user.is_deleted:
        user.is_deleted = False
        changed = True
    if (user.outlook_sync_permission or "") != sync_perm:
        user.outlook_sync_permission = sync_perm
        counters["permissions_updated"] += 1
        changed = True
    if not (user.password_hash or "").strip():
        user.password_hash = hash_password(DEFAULT_PASSWORD)
        changed = True
    if not (user.username or "").strip():
        user.username = _ensure_username(db, preferred_username, email, exclude_user_id=user.id)
        changed = True

    if changed:
        counters["users_updated"] += 1
    db.flush()
    return user


def upsert_segments(
    db: Session,
    user: User,
    segments: Sequence[str],
    counters: Dict[str, int],
) -> None:
    wanted = sorted({(s or "").strip() for s in segments if (s or "").strip()}, key=str.casefold)
    existing = {
        (row.segment or "").strip(): row
        for row in db.scalars(select(UserSegment).where(UserSegment.user_id == user.id)).all()
        if (row.segment or "").strip()
    }

    for seg in wanted:
        row = existing.get(seg)
        if row is None:
            # case-insensitive match
            row = next(
                (r for k, r in existing.items() if k.casefold() == seg.casefold()),
                None,
            )
        if row is None:
            db.add(
                UserSegment(
                    user_id=user.id,
                    segment=seg,
                    active=True,
                    retain_history=False,
                )
            )
            counters["segment_links"] += 1
            continue
        if not row.active or row.segment != seg:
            row.segment = seg
            row.active = True
            counters["segment_links"] += 1

    wanted_cf = {s.casefold() for s in wanted}
    for key, row in existing.items():
        if key.casefold() not in wanted_cf and row.active:
            row.active = False
            counters["segment_links"] += 1
    db.flush()


def get_or_create_distributor(db: Session, company: str, counters: Dict[str, int]) -> Distributor:
    raw = (company or "").strip()
    norm = normalize_company_name(raw) or raw
    dist = db.scalar(
        select(Distributor).where(
            Distributor.is_deleted.is_(False),
            func.lower(func.trim(Distributor.company)) == norm.casefold(),
        )
    )
    if dist is None:
        dist = db.scalar(
            select(Distributor).where(
                Distributor.is_deleted.is_(False),
                func.lower(func.trim(Distributor.name)) == norm.casefold(),
            )
        )
    if dist is not None:
        return dist

    dist = Distributor(
        name=raw,
        company=raw,
        is_active=True,
        is_deleted=False,
    )
    db.add(dist)
    db.flush()
    counters["distributors_created"] += 1
    return dist


def ensure_user_distributor(
    db: Session,
    user: User,
    distributor: Distributor,
    counters: Dict[str, int],
) -> None:
    exists = db.scalar(
        select(UserDistributor.id).where(
            UserDistributor.user_id == user.id,
            UserDistributor.distributor_id == distributor.id,
        )
    )
    if exists is not None:
        return
    db.add(
        UserDistributor(
            user_id=user.id,
            distributor_id=distributor.id,
            assigned_by=None,
        )
    )
    db.flush()
    counters["distributor_mappings"] += 1


def seed(db: Session) -> Tuple[Dict[str, int], Dict[str, int]]:
    counters = {
        "users_created": 0,
        "users_updated": 0,
        "permissions_updated": 0,
        "segment_links": 0,
        "distributor_mappings": 0,
        "distributors_created": 0,
    }

    for persona in PERSONA_SEED:
        user = upsert_user(db, persona, counters)
        upsert_segments(db, user, persona.get("segments") or [], counters)
        for company in persona.get("distributors") or []:
            dist = get_or_create_distributor(db, str(company), counters)
            ensure_user_distributor(db, user, dist, counters)

    db.commit()

    totals = {
        "roles": 3,  # Super Admin (system) + Admin + Sales User — no roles table
        "users": int(
            db.scalar(
                select(func.count()).select_from(User).where(User.is_deleted.is_(False))
            )
            or 0
        ),
        "segments": len(BUSINESS_SEGMENTS),
        "distributor_mappings": int(
            db.scalar(select(func.count()).select_from(UserDistributor)) or 0
        ),
        "permissions_updated": int(
            db.scalar(
                select(func.count())
                .select_from(User)
                .where(
                    User.is_deleted.is_(False),
                    User.outlook_sync_permission.is_not(None),
                )
            )
            or 0
        ),
    }
    return counters, totals


def main() -> None:
    db = SessionLocal()
    try:
        _counters, totals = seed(db)
        print("====================================")
        print("APCOTEX UAT SEED COMPLETED")
        print("====================================")
        print()
        print(f"Roles               : {totals['roles']}")
        print(f"Users               : {totals['users']}")
        print(f"Segments            : {totals['segments']}")
        print(f"Distributor Mappings: {totals['distributor_mappings']}")
        print(f"Permissions Updated : {totals['permissions_updated']}")
        print()
        print("Database Ready for UAT")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
