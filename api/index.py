"""Serverless entrypoint for the Vercel Python runtime.

Exports the FastAPI ASGI app. Vercel routes every request here, including
the page, /api/health, and /api/run. Keys come from the environment.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if _SRC.is_dir():
    src = str(_SRC)
    if src not in sys.path:
        sys.path.insert(0, src)

from agroclima_agent.web.app import app

__all__ = ["app"]
