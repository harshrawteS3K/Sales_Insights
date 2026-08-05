# APCOTEX Sales Insights — Backend

Enterprise FastAPI backend for Apcotex Industries Sales Insights platform.

## Stack

- Python 3.11+
- FastAPI + Uvicorn
- PostgreSQL + SQLAlchemy 2.0 + Alembic
- Pydantic v2 / Pydantic Settings
- Microsoft Graph (MSAL)
- Pandas + OpenPyXL
- Loguru

## Quick start

```bash
cd backend
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Linux / macOS

pip install -r requirements.txt

# Ensure PostgreSQL database `apcotex_salesinsights` exists and `.env` is configured.

alembic revision --autogenerate -m "initial_schema"
alembic upgrade head

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Swagger UI: http://localhost:8000/docs

## Environment

Configure secrets in `.env` (never commit secrets). See `.env.example`.

| Variable | Purpose |
|----------|---------|
| `APP_HOST` | Bind address (UAT: `0.0.0.0`) |
| `APP_PORT` | Listen port (UAT: `8000`) |
| `CORS_ORIGINS` | Comma-separated browser origins (include `http://<SERVER-IP>:5173` for UAT) |
| `DATABASE_URL` | PostgreSQL connection string |
| `GRAPH_TENANT_ID` | Azure AD tenant |
| `GRAPH_CLIENT_ID` | App registration client id |
| `GRAPH_CLIENT_SECRET` | App registration secret |
| `GRAPH_MAILBOX` | Shared mailbox to sync |
| `SUPER_ADMIN_USERNAME` / `SUPER_ADMIN_PASSWORD` | Env-only Super Admin |

### UAT start (Windows)

```powershell
alembic upgrade head
python run.py
# or: uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Swagger UI: http://localhost:8000/docs (or http://\<SERVER-IP\>:8000/docs on VPN)

## RBAC (Phase 1)

No JWT yet. Pass role headers for authorization hooks:

- `X-User-Role`: `admin` | `user`
- `X-User-Name`: display name
- `X-User-Id`: optional numeric user id

Admin-only endpoints (users write, master uploads, outlook sync, etc.) require `X-User-Role: admin`.

## Frontend contract routes (`/api/...`)

Prepared for Phase 2 React integration (no frontend changes in Phase 1):

| Frontend service | Backend route |
|------------------|---------------|
| Emails | `GET /api/emails` |
| Consolidated records | `GET /api/consolidated-data/records` |
| Distributor details | `GET /api/consolidated-data/distributors` |
| Reports | `GET /api/reports` |
| Report filters | `GET /api/reports/filter-categories` |
| Audit trail | `GET /api/audit-trail` |
| Visualizations | `GET /api/visualizations/*` |
| Dashboard | `GET /api/dashboard/summary` |
| Outlook sync | `POST /api/outlook/sync` |
| Master data | `POST /api/master-data/*/upload` |

Versioned aliases are also mounted under `/api/v1/...`.

## Architecture

```
app/
  api/v1/endpoints/   # HTTP adapters
  services/           # Business logic
  repositories/       # Data access (Repository Pattern)
  models/             # SQLAlchemy ORM
  schemas/            # Pydantic request/response models
  integrations/       # Graph + Excel
  dependencies/       # DI + RBAC
  middleware/         # Request logging
  exceptions/         # Global error handling
```

## AWS EC2 deployment notes

1. Install Python 3.11+, PostgreSQL client libs, and create a systemd unit for uvicorn / gunicorn.
2. Set `APP_ENV=production`, `DEBUG=false`, and production `CORS_ORIGINS`.
3. Point `DATABASE_URL` at RDS (or local Postgres) and run `alembic upgrade head`.
4. Place Graph secrets in environment / AWS Secrets Manager — never bake into the image.
5. Persist `uploads/`, `downloads/`, and `logs/` on a durable volume.

Example process:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

## License

Proprietary — Apcotex Industries / internal use.
