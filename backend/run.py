"""
Uvicorn entrypoint that reuses APP_HOST / APP_PORT from Settings (.env).

Usage (Windows UAT):
    python run.py

Equivalent CLI:
    uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import uvicorn

from app.core.config import settings


def main() -> None:
    uvicorn.run(
        "app.main:app",
        host=settings.app_host or "0.0.0.0",
        port=int(settings.app_port or 8000),
        reload=False,
    )


if __name__ == "__main__":
    main()
