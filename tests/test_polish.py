"""Polish: Spanish consult copy, fallback status, frozen vision id, no vendor names."""

import json
from datetime import datetime, timezone
from io import BytesIO

import httpx
from PIL import Image

from agroclima_agent.alerts import AlertSearch
from agroclima_agent.audit import AuditLog
from agroclima_agent.config import Settings
from agroclima_agent.frozen_vision import load_frozen_vision
from agroclima_agent.nebius import NebiusClient
from agroclima_agent.open_meteo import FixtureSource
from agroclima_agent.pipeline import STATUS_FALLBACK, STATUS_LIVE, run_agent, strip_vendor_names
from agroclima_agent.places import places_in
from agroclima_agent.risk import synthetic_forecast
from agroclima_agent.web.app import create_app

OLD_TECNICO = "No technician number is configured"
SPANISH_TECNICO = (
    "Para una visita, comuníquese con el técnico de su cooperativa "
    "o de la oficina agrícola más cercana."
)
VENDORS = ("Tavily", "Nebius", "NVIDIA", "Nemotron", "Open-Meteo", "OpenAI", "Token Factory")


def _settings(tmp_path, **overrides):
    values = dict(
        nebius_api_key="test-key-not-real",
        nebius_base_url="https://api.tokenfactory.nebius.com/v1",
        tavily_api_key=None,
        model_nano="nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B",
        model_plan="nvidia/nemotron-3-super-120b-a12b",
        model_vision="nvidia/not-the-frozen-model",
        audit_log=tmp_path / "audit.jsonl",
        host="127.0.0.1",
        port=8000,
        open_meteo_base_url="https://api.open-meteo.com/v1/forecast",
        tavily_cache_path=tmp_path / "cache.json",
        tavily_counter_path=tmp_path / "counter.json",
        technician_whatsapp=None,
    )
    values.update(overrides)
    return Settings(**values)


def _png(color: tuple[int, int, int]) -> bytes:
    image = Image.new("RGB", (64, 64), color)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _ok(text: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": text}}],
            "usage": {"prompt_tokens": 4, "completion_tokens": 4, "total_tokens": 8},
        },
    )


def _user_text(body: dict) -> str:
    content = body["messages"][-1]["content"]
    if isinstance(content, str):
        return content
    return "\n".join(part.get("text", "") for part in content if isinstance(part, dict))


def _farmer_bits(result) -> str:
    chunks = []
    for step in result.steps:
        chunks.append(step.farmer_text)
        for cite in step.citations:
            chunks.append(cite.title)
            chunks.append(cite.snippet)
    return "\n".join(chunks)


def test_tecnico_section_is_spanish(tmp_path):
    page = create_app(_settings(tmp_path), FixtureSource(synthetic_forecast()))
    html = __import__("fastapi").testclient.TestClient(page).get("/").text
    assert OLD_TECNICO not in html
    assert "Ask your cooperative" not in html
    assert SPANISH_TECNICO in html
    assert "Finished with live services." not in html
    assert "Nebius" not in html
    assert "Tavily" not in html


def test_fallback_status_names_the_backup(tmp_path):
    settings = _settings(tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        if body["model"] == load_frozen_vision()["model"]:
            raise httpx.ReadTimeout("vision timeout")
        return _ok("El riesgo de roya en Santa Ana es alto según el pronóstico.")

    audit = AuditLog(settings.audit_log)
    result = run_agent(
        settings=settings,
        department="Santa Ana",
        places=places_in("Santa Ana"),
        source=FixtureSource(synthetic_forecast()),
        image=_png((220, 100, 20)),
        media_type="image/png",
        question=None,
        audit=audit,
        client=NebiusClient(settings, audit, transport=httpx.MockTransport(handler)),
        alerts=AlertSearch(settings, audit),
    )
    assert result.mock is False
    assert result.used_fallback is True
    assert result.status == STATUS_FALLBACK
    assert result.steps[1].farmer_text.startswith("Alertas sin actualizar hoy")
    assert result.steps[2].detail["path"] == "colour-lr"
    shown = _farmer_bits(result)
    for name in VENDORS:
        assert name.lower() not in shown.lower()


def test_live_status_when_nothing_fell_back(tmp_path):
    settings = _settings(tmp_path, tavily_api_key="tavily-test")
    settings.tavily_cache_path.write_text(
        json.dumps(
            {
                "Santa Ana": {
                    "query": "alerta",
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                    "citations": [
                        {
                            "title": "Boletín CENTA",
                            "url": "https://www.centa.gob.sv/roya",
                            "snippet": "Revise las hojas esta semana.",
                            "official": True,
                            "mock": False,
                            "stale": False,
                        }
                    ],
                }
            }
        ),
        encoding="utf-8",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert "tavily.com" not in str(request.url)
        body = json.loads(request.content.decode())
        text = _user_text(body)
        if "Escriba en español" in text:
            return _ok("El riesgo de roya en Santa Ana es alto según Tavily.")
        if body["model"] == settings.model_plan:
            return _ok("El riesgo es alto. Avise a su agrónomo.")
        return _ok("Hay un boletín oficial para leer esta semana.")

    audit = AuditLog(settings.audit_log)
    result = run_agent(
        settings=settings,
        department="Santa Ana",
        places=places_in("Santa Ana"),
        source=FixtureSource(synthetic_forecast()),
        image=None,
        media_type=None,
        question=None,
        audit=audit,
        client=NebiusClient(settings, audit, transport=httpx.MockTransport(handler)),
        alerts=AlertSearch(settings, audit),
    )
    assert result.mock is False
    assert result.used_fallback is False
    assert result.status == STATUS_LIVE
    clima = result.steps[0].farmer_text
    assert "Tavily" not in clima
    assert "alto" in clima
    assert "Open-Meteo" not in result.steps[0].citations[0].title
    for name in VENDORS:
        assert name.lower() not in _farmer_bits(result).lower()
    logged = settings.audit_log.read_text(encoding="utf-8")
    assert "tavily-cache" in logged


def test_health_reports_the_frozen_vision_model(tmp_path):
    frozen = load_frozen_vision()["model"]
    settings = _settings(tmp_path, model_vision="nvidia/not-the-frozen-model")
    body = __import__("fastapi").testclient.TestClient(
        create_app(settings, FixtureSource(synthetic_forecast()))
    ).get("/api/health").json()
    assert body["models"]["vision"] == frozen
    assert body["models"]["vision"] != settings.model_vision
    assert "nebius" in body["base_url"]


def test_vendor_words_are_stripped_from_farmer_sentences():
    cleaned = strip_vendor_names("Según Tavily y Nebius, el riesgo es alto.")
    assert "Tavily" not in cleaned
    assert "Nebius" not in cleaned
    assert "alto" in cleaned
