"""One-command web UI: python -m agroclima_agent"""

from __future__ import annotations

import threading

import uvicorn

from agroclima_agent.config import load_settings


def _refresh_alerts_once() -> None:
    """Fill the alert cache at startup. refresh() keeps the 24 h and Tavily budget guards."""
    from agroclima_agent.jobs.refresh_alerts import main as refresh_main

    try:
        refresh_main()
    except Exception as exc:  # never block the web UI on alerts
        print(f"alert refresh failed: {type(exc).__name__}", flush=True)


def main() -> None:
    settings = load_settings()
    if settings.tavily_configured:
        threading.Thread(target=_refresh_alerts_once, daemon=True).start()
    uvicorn.run(
        "agroclima_agent.web.app:app",
        host=settings.host,
        port=settings.port,
        factory=False,
    )


if __name__ == "__main__":
    main()
