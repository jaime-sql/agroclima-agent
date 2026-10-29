"""HTTP API and the four-step page."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from agroclima_agent.audit import AuditLog, tavily_usage
from agroclima_agent.config import Settings, load_settings
from agroclima_agent.web.limits import (
    RunGuard,
    client_ip,
    farmer_model_id,
    guard_message,
    normalize_lang,
)
from agroclima_agent.diagnosis import CONSULT_LABEL
from agroclima_agent.frozen_vision import load_frozen_vision
from agroclima_agent.handoff import technician_href
from agroclima_agent.open_meteo import ForecastSource, OpenMeteoSource
from agroclima_agent.pipeline import run_agent
from agroclima_agent.places import departments, places_in

STATIC = Path(__file__).resolve().parent / "static"
MAX_BYTES = 5 * 1024 * 1024
FAVICON_SVG = (
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'>"
    "<path fill='#1e5b2a' d='M16 3c1.2 6 6.5 8.2 10 12-5 1.6-8 6.4-10 14"
    "C14.2 21.4 9 16.6 6 15 9.2 11.2 14.6 9 16 3z'/></svg>"
)


def create_app(
    settings: Settings | None = None,
    source: ForecastSource | None = None,
    guard: RunGuard | None = None,
) -> FastAPI:
    settings = settings or load_settings()
    source = source or OpenMeteoSource(settings)
    guard = guard or RunGuard(daily_cap=settings.daily_run_cap)
    app = FastAPI(title="AgroClima Agent", version="0.1.0")
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.exception_handler(RequestValidationError)
    async def missing_form(request: Request, _exc: RequestValidationError) -> JSONResponse:
        language = "es"
        try:
            form = await request.form()
            language = normalize_lang(str(form.get("language") or "es"))
        except Exception:
            language = "es"
        return JSONResponse(
            status_code=422,
            content={"detail": guard_message("missing", language)},
        )

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> Response:
        return Response(content=FAVICON_SVG, media_type="image/svg+xml")

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
                "vision": load_frozen_vision()["model"],
            },
            "consult_label": CONSULT_LABEL,
            "consult_href": technician_href(
                settings.technician_whatsapp,
                "Consulta sobre roya del cafeto",
            ),
        }

    @app.get("/api/departments")
    def list_departments() -> dict:
        return {"departments": departments()}

    @app.get("/api/tavily-usage")
    def tavily_usage_view() -> dict:
        return tavily_usage(settings.audit_log)

    @app.post("/api/run")
    async def run(
        request: Request,
        department: str = Form(...),
        question: str = Form(""),
        language: str = Form("es"),
        photo: UploadFile | None = File(None),
    ) -> dict:
        lang = normalize_lang(language)
        if not guard.allow_ip(client_ip(request)):
            raise HTTPException(status_code=429, detail=guard_message("rate", lang))
        selected = places_in(department)
        if not selected:
            raise HTTPException(status_code=400, detail=guard_message("department", lang))
        image = None
        media_type = None
        if photo is not None and photo.filename:
            raw = await photo.read()
            if len(raw) > MAX_BYTES:
                raise HTTPException(status_code=400, detail=guard_message("photo_size", lang))
            media_type = _sniff(raw)
            if media_type is None:
                raise HTTPException(status_code=400, detail=guard_message("photo_type", lang))
            image = raw
        if not guard.allow_daily():
            raise HTTPException(status_code=429, detail=guard_message("daily", lang))
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
            language=lang,
        )
        payload = result.as_dict()
        for step in payload["steps"]:
            step["model_id"] = farmer_model_id(step.get("model_id"))
        return payload

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
