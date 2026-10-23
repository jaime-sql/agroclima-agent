"""HTTP API and the four-step page."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from agroclima_agent.audit import AuditLog
from agroclima_agent.config import Settings, load_settings
from agroclima_agent.open_meteo import ForecastSource, OpenMeteoSource
from agroclima_agent.pipeline import run_agent
from agroclima_agent.places import departments, places_in

STATIC = Path(__file__).resolve().parent / "static"
MAX_BYTES = 5 * 1024 * 1024


def create_app(settings: Settings | None = None, source: ForecastSource | None = None) -> FastAPI:
    settings = settings or load_settings()
    source = source or OpenMeteoSource(settings)
    app = FastAPI(title="AgroClima Agent", version="0.1.0")
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    @app.get("/api/health")
    def health() -> dict:
        return {
            "ok": True,
            "mock": settings.mock,
            "mock_reasons": settings.mock_reasons(),
            "nebius_configured": settings.nebius_configured,
            "tavily_configured": settings.tavily_configured,
            "base_url": settings.nebius_base_url,
            "models": {
                "nano": settings.model_nano,
                "plan": settings.model_plan,
                "vision": settings.model_vision,
            },
        }

    @app.get("/api/departments")
    def list_departments() -> dict:
        return {"departments": departments()}

    @app.post("/api/run")
    async def run(
        department: str = Form(...),
        question: str = Form(""),
        photo: UploadFile | None = File(None),
    ) -> dict:
        selected = places_in(department)
        if not selected:
            raise HTTPException(status_code=400, detail="Unknown department")
        image = None
        media_type = None
        if photo is not None and photo.filename:
            raw = await photo.read()
            if len(raw) > MAX_BYTES:
                raise HTTPException(status_code=400, detail="Photo is larger than 5 MB")
            media_type = _sniff(raw)
            if media_type is None:
                raise HTTPException(status_code=400, detail="Photo must be JPEG, PNG, or WebP")
            image = raw
        audit = AuditLog(settings.audit_log)
        result = run_agent(
            settings=settings,
            department=department,
            places=selected,
            source=source,
            image=image,
            media_type=media_type,
            question=question,
            audit=audit,
        )
        return result.as_dict()

    return app


def _sniff(raw: bytes) -> str | None:
    if raw.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(raw) >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    return None


app = create_app()
