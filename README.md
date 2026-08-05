# APCOTEX Sales Insights

Enterprise Sales Insights platform.

## Structure

- `frontend/` — React + Vite application
- `backend/` — FastAPI application

## Local development

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Vite binds to `0.0.0.0:5173`.  
If `VITE_API_BASE_URL` is unset, the client calls `{page-hostname}:8000/api` automatically (localhost, LAN, and VPN IPs all work).

### Backend

```bash
cd backend
venv\Scripts\activate
copy .env.example .env
# Edit .env — do not commit secrets
alembic upgrade head
python run.py
# or: uvicorn app.main:app --host 0.0.0.0 --port 8000
```

`APP_HOST` / `APP_PORT` in `.env` are used by `python run.py` (default `0.0.0.0:8000`).

---

## Windows Server UAT (VPN)

Users open: `http://<SERVER-IP>:5173`  
API: `http://<SERVER-IP>:8000`

### 1. Backend `.env`

Keep Graph/DB secrets as-is. Ensure:

```env
APP_HOST=0.0.0.0
APP_PORT=8000
# Local + UAT together (replace <SERVER-IP>; keep localhost for on-server testing)
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://<SERVER-IP>:5173
```

Replace `<SERVER-IP>` with the real address (e.g. `10.0.3.213`). If the Vite Origin is missing from this list, login OPTIONS preflight returns HTTP 400 and POST never runs.

### 2. Frontend env

Optional. Leave `VITE_API_BASE_URL` **unset** so the UI auto-calls `http://<SERVER-IP>:8000/api` when users open `http://<SERVER-IP>:5173`.

Override only if the API is on a different host/port:

```powershell
cd frontend
# optional:
# $env:VITE_API_BASE_URL = "http://<API-HOST>:8000/api"
```

### 3. First-time DB migrate

```powershell
cd backend
.\venv\Scripts\activate
alembic upgrade head
```

### 4. Start services

**Backend**

```powershell
cd backend
.\venv\Scripts\activate
python run.py
# equivalent:
# uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Or: `.\scripts\start_uat.ps1`

**Frontend**

```powershell
cd frontend
npm run dev
# equivalent: vite --host 0.0.0.0 --port 5173
# API host is derived from the browser URL (no VITE_API_BASE_URL required)
```

Or: `.\scripts\start_uat.ps1`

### 5. Firewall

Allow inbound TCP **5173** and **8000** for the VPN subnet.

### Checklist

- [ ] React: `http://<SERVER-IP>:5173`
- [ ] API health: `http://<SERVER-IP>:8000/api/health`
- [ ] Login works
- [ ] Outlook sync / Master Data / Quarterly / Audit / uploads / downloads
- [ ] PostgreSQL still on localhost (same server)
