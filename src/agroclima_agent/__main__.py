"""One-command web UI: python -m agroclima_agent"""

from __future__ import annotations

import uvicorn

from agroclima_agent.config import load_settings


def main() -> None:
    settings = load_settings()
    uvicorn.run(
        "agroclima_agent.web.app:app",
        host=settings.host,
        port=settings.port,
        factory=False,
    )


if __name__ == "__main__":
    main()
