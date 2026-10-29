"""QA fixes: empty class lists, non-leaf colour gate, per-service mock, labels."""

import json
from io import BytesIO

import httpx
from PIL import Image

from agroclima_agent.alerts import AlertSearch
from agroclima_agent.audit import AuditLog
from agroclima_agent.config import Settings
from agroclima_agent.diagnosis import RETAKE_COPY, public_leaf_copy
from agroclima_agent.frozen_vision import load_frozen_vision
from agroclima_agent.histogram import read_histogram
from agroclima_agent.nebius import NebiusClient
from agroclima_agent.open_meteo import FixtureSource
from agroclima_agent.pipeline import TEMPLATE_MODEL, hide_empty_fungicide_sentence, run_agent
from agroclima_agent.places import places_in
from agroclima_agent.risk import synthetic_forecast
from agroclima_agent.web.app import create_app


def _settings(tmp_path, **overrides):
    values = dict(
        nebius_api_key="test-key-not-real",
        nebius_base_url="https://api.tokenfactory.nebius.com/v1",
        tavily_api_key=None,
        model_nano="nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B",
        model_plan="nvidia/nemotron-3-super-120b-a12b",
        model_vision="nvidia/Nemotron-3.5-Super-VL",
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


def _user_text(body: dict) -> str:
    content = body["messages"][-1]["content"]
    if isinstance(content, str):
        return content
    return "\n".join(part.get("text", "") for part in content if isinstance(part, dict))


def _ok(text: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": text}}],
            "usage": {"prompt_tokens": 4, "completion_tokens": 4, "total_tokens": 8},
        },
    )


def test_empty_fungicide_list_is_omitted_from_the_plan(tmp_path):
    assert hide_empty_fungicide_sentence(
        "Las clases de fungicidas indicadas son: [] . El riesgo es alto.",
        (),
    ) == "El riesgo es alto."
    settings = _settings(tmp_path)
    question = "¿Debo preocuparme por la roya esta semana?"

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        text = _user_text(body)
        if body["model"] == load_frozen_vision()["model"]:
            raise httpx.ReadTimeout("vision timeout")
        if "Pregunta del caficultor" in text:
            return _ok("El pronóstico de la semana es de riesgo alto.")
        if body["model"] == settings.model_plan:
            assert "fungicide_classes" not in text
            return _ok("Las clases de fungicidas indicadas son: [] .")
        return _ok("El riesgo de roya en Santa Ana es alto según el pronóstico.")

    audit = AuditLog(settings.audit_log)
    client = NebiusClient(settings, audit, transport=httpx.MockTransport(handler))
    result = run_agent(
        settings=settings,
        department="Santa Ana",
        places=places_in("Santa Ana"),
        source=FixtureSource(synthetic_forecast()),
        image=_png((220, 100, 20)),
        media_type="image/png",
        question=question,
        audit=audit,
        client=client,
        alerts=AlertSearch(settings, audit),
    )
    plan = result.steps[3].farmer_text
    assert "[]" not in plan
    assert "{" not in plan
    assert "fungicid" not in plan.lower()
    assert "Las clases de fungicidas" not in plan


def test_colour_fallback_non_leaf_reuses_the_main_retake_text():
    orange = _png((220, 100, 20))
    read = read_histogram(orange)
    assert read.label == "retomar"
    assert read.retake_reason == "no_hoja"
    farmer = public_leaf_copy(read)
    assert farmer == public_leaf_copy(read)
    assert RETAKE_COPY["no_hoja"][0] in farmer
    assert farmer.startswith("Repetir foto. No vemos una hoja de café.")
    assert "Parece roya" not in farmer


def test_missing_tavily_key_does_not_mock_the_app(tmp_path):
    settings = _settings(tmp_path, tavily_api_key=None, nebius_api_key="test-key-not-real")
    app = create_app(settings, FixtureSource(synthetic_forecast()))
    client_http = __import__("fastapi").testclient.TestClient(app)
    health = client_http.get("/api/health").json()
    assert health["mock"] is False
    assert health["mock_reasons"] == []
    assert health["tavily_configured"] is False
    page = client_http.get("/").text
    assert 'id="consult-tecnico"' in page
    assert "Consultar a un técnico" in page
    assert 'href="#tecnico"' in page
    assert 'id="banner" class="banner" hidden' in page

    def handler(request: httpx.Request) -> httpx.Response:
        assert "tavily" not in str(request.url)
        return _ok("El riesgo de roya en Santa Ana es alto según el pronóstico.")

    audit = AuditLog(settings.audit_log)
    client = NebiusClient(settings, audit, transport=httpx.MockTransport(handler))
    result = run_agent(
        settings=settings,
        department="Santa Ana",
        places=places_in("Santa Ana"),
        source=FixtureSource(synthetic_forecast()),
        image=None,
        media_type=None,
        question=None,
        audit=audit,
        client=client,
        alerts=AlertSearch(settings, audit),
    )
    assert result.mock is False
    alerts = result.steps[1]
    assert alerts.mock is False
    assert alerts.farmer_text == "No encontramos una alerta oficial para Santa Ana."
    assert "guardadas" not in alerts.farmer_text
    assert "visita anterior" not in alerts.farmer_text
    assert alerts.citations[0].stale is True
    assert "nvidia/" not in (alerts.model_id or "")


def test_labels_name_the_model_or_the_template(tmp_path):
    frozen_model = load_frozen_vision()["model"]
    settings = _settings(tmp_path, model_vision="nvidia/not-the-frozen-model")

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        text = _user_text(body)
        if body["model"] == frozen_model:
            assert body["model"] != settings.model_vision
            return _ok('{"label":"sana","confidence":0.9}')
        if text.startswith("Escriba en español"):
            return _ok("Usted ha decidido que el nivel de roya en Santa Ana es alto")
        if body["model"] == settings.model_plan:
            return _ok("Las clases de fungicidas indicadas son: [].")
        return _ok("Semana alta. Consulte a su agrónomo.")

    audit = AuditLog(settings.audit_log)
    client = NebiusClient(settings, audit, transport=httpx.MockTransport(handler))
    result = run_agent(
        settings=settings,
        department="Santa Ana",
        places=places_in("Santa Ana"),
        source=FixtureSource(synthetic_forecast()),
        image=_png((30, 140, 40)),
        media_type="image/png",
        question=None,
        audit=audit,
        client=client,
        alerts=AlertSearch(settings, audit),
    )
    assert result.steps[2].model_id == frozen_model
    assert result.steps[2].model_id != settings.model_vision
    assert result.steps[0].model_id == TEMPLATE_MODEL
    assert "nvidia/" not in result.steps[0].model_id
    assert result.steps[3].model_id == TEMPLATE_MODEL
    assert settings.model_plan not in result.steps[3].model_id


def test_probability_wording_is_rewritten_to_risk_levels(tmp_path):
    settings = _settings(tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        text = _user_text(body)
        if body["model"] == settings.model_nano and text.startswith("Escriba en español"):
            assert "probabilidad" in body["messages"][0]["content"]
            return _ok("Hay una alta probabilidad (80%) de roya.")
        return _ok("El riesgo de roya en Santa Ana es alto según el pronóstico.")

    audit = AuditLog(settings.audit_log)
    client = NebiusClient(settings, audit, transport=httpx.MockTransport(handler))
    result = run_agent(
        settings=settings,
        department="Santa Ana",
        places=places_in("Santa Ana"),
        source=FixtureSource(synthetic_forecast()),
        image=None,
        media_type=None,
        question="¿Cómo sigue la semana?",
        audit=audit,
        client=client,
        alerts=AlertSearch(settings, audit),
    )
    clima = result.steps[0].farmer_text
    assert "probabilidad" not in clima.lower()
    assert "%" not in clima
    assert "riesgo alto" in clima


def test_consult_link_uses_env_or_an_anchor(tmp_path):
    unset = _settings(tmp_path, technician_whatsapp=None)
    health = create_app(unset, FixtureSource(synthetic_forecast()))
    body = __import__("fastapi").testclient.TestClient(health).get("/api/health").json()
    assert body["consult_label"] == "Consultar a un técnico"
    assert body["consult_href"] == "#tecnico"
    assert "wa.me" not in body["consult_href"]

    numbered = _settings(tmp_path, technician_whatsapp="503 7000-0000")
    href = create_app(numbered, FixtureSource(synthetic_forecast()))
    linked = __import__("fastapi").testclient.TestClient(href).get("/api/health").json()["consult_href"]
    assert linked.startswith("https://wa.me/50370000000?text=")
    assert "wa.me/?" not in linked
