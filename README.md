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
copy .env.example .env.local
npm run dev
```

Vite binds to `0.0.0.0:5173`. API URL comes from `VITE_API_BASE_URL` (defaults to `http://localhost:8000/api` if unset).

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
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://<SERVER-IP>:5173
```

Replace `<SERVER-IP>` with the real server address (e.g. `10.0.3.213`).

### 2. Frontend env

```powershell
cd frontend
copy .env.example .env.local
# Set:
# VITE_API_BASE_URL=http://<SERVER-IP>:8000/api
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
$env:VITE_API_BASE_URL = "http://<SERVER-IP>:8000/api"
npm run dev
# equivalent: vite --host 0.0.0.0 --port 5173
```

Or: `.\scripts\start_uat.ps1` (after setting `VITE_API_BASE_URL`)

### 5. Firewall

Allow inbound TCP **5173** and **8000** for the VPN subnet.

### Checklist

- [ ] React: `http://<SERVER-IP>:5173`
- [ ] API health: `http://<SERVER-IP>:8000/api/health`
- [ ] Login works
- [ ] Outlook sync / Master Data / Quarterly / Audit / uploads / downloads
- [ ] PostgreSQL still on localhost (same server)
