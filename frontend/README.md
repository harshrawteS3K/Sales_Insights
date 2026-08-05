# APCOTEX Sales Insights — Frontend

React + Vite application for Apcotex Sales Insights.

## Setup

```bash
cd frontend
npm install
copy .env.example .env.local
npm run dev
```

Vite listens on **0.0.0.0:5173** (VPN / Windows Server friendly).

## Environment

| Variable | Purpose |
|----------|---------|
| `VITE_API_BASE_URL` | **Optional** override for backend API base (must include `/api`) |

**Default (recommended for UAT):** leave unset. The client uses:

`{window.location.protocol}//{window.location.hostname}:8000/api`

Examples of auto-derived URLs:

| Browser opens | API called |
|---------------|------------|
| `http://localhost:5173` | `http://localhost:8000/api` |
| `http://192.168.0.107:5173` | `http://192.168.0.107:8000/api` |
| `http://10.0.3.213:5173` | `http://10.0.3.213:8000/api` |

Set `VITE_API_BASE_URL` only when the API host/port differs from that pattern.

Ensure backend `CORS_ORIGINS` includes the Origin users open (see `backend/.env.example`).

## Scripts

- `npm run dev` — Vite on `0.0.0.0:5173`
- `npm run build` — production build
- `npm run preview` — preview build on `0.0.0.0:5173`
- `.\scripts\start_uat.ps1` — UAT helper (optional `VITE_API_BASE_URL`)

## Structure

See `src/` for pages, components, services, routes, and styles.
