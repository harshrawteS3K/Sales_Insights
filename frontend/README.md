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
| `VITE_API_BASE_URL` | Backend API base including `/api` |

Examples:

- Local: `http://localhost:8000/api`
- UAT: `http://<SERVER-IP>:8000/api`

If unset, the client falls back to `http://localhost:8000/api`.

## Scripts

- `npm run dev` — Vite on `0.0.0.0:5173`
- `npm run build` — production build
- `npm run preview` — preview build on `0.0.0.0:5173`
- `.\scripts\start_uat.ps1` — UAT helper (set `VITE_API_BASE_URL` first)

## Structure

See `src/` for pages, components, services, routes, and styles.
