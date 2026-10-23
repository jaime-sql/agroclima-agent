"""Trust-panel lines name the model that answered the leaf photo."""

import json
from io import BytesIO

import httpx
from PIL import Image

from agroclima_agent.alerts import AlertSearch
from agroclima_agent.audit import AuditLog
from agroclima_agent.config import Settings
from agroclima_agent.diagnosis import CONSULT_LABEL, ORIENTATION_TAG
from agroclima_agent.nebius import NebiusClient
from agroclima_agent.open_meteo import FixtureSource
from agroclima_agent.pipeline import run_agent
from agroclima_agent.places import places_in
from agroclima_agent.risk import synthetic_forecast
from agroclima_agent.trust_sentences import COLOUR_TRUST_SENTENCE, NEMOTRON_TRUST_SENTENCE

# Verbatim from results.md on PR #2, without the trailing orientation sentence.
EXPECTED_NEMOTRON = 'Probado con 252 fotos públicas de hojas de café de Brasil (no de El Salvador), fotografiadas sobre fondo blanco, no en el campo: acertó roya o no roya en 89% (IC 95%: 85–93%), frente a 81% de un modelo simple de color. Detecta 78% de las hojas con roya: se le escapa cerca de 1 de cada 5.'
EXPECTED_COLOUR = 'Probado con 252 fotos públicas de hojas de café de Brasil (no de El Salvador), fotografiadas sobre fondo blanco, no en el campo: acertó roya o no roya en 81% (IC 95%: 76–86%). Detecta 79% de las hojas con roya: se le escapa cerca de 1 de cada 5.'
TAG_TAIL = "Orientativo — no es un diagnóstico."


def test_constants_are_the_results_lines_without_the_trailing_tag():
    assert NEMOTRON_TRUST_SENTENCE == EXPECTED_NEMOTRON
    assert COLOUR_TRUST_SENTENCE == EXPECTED_COLOUR
    assert TAG_TAIL not in NEMOTRON_TRUST_SENTENCE
    assert TAG_TAIL not in COLOUR_TRUST_SENTENCE
    assert "fotografiadas sobre fondo blanco, no en el campo" in NEMOTRON_TRUST_SENTENCE
    assert "fotografiadas sobre fondo blanco, no en el campo" in COLOUR_TRUST_SENTENCE
    assert "tomadas en laboratorio" not in NEMOTRON_TRUST_SENTENCE
    assert "tomadas en laboratorio" not in COLOUR_TRUST_SENTENCE
    assert "89%" in NEMOTRON_TRUST_SENTENCE
    assert "Detecta 78% de las hojas con roya: se le escapa cerca de 1 de cada 5." in NEMOTRON_TRUST_SENTENCE
    assert "89%" not in COLOUR_TRUST_SENTENCE
    assert "Detecta 79% de las hojas con roya: se le escapa cerca de 1 de cada 5." in COLOUR_TRUST_SENTENCE


def _settings(tmp_path, **overrides):
    values = dict(
        nebius_api_key=None,
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
    )
    values.update(overrides)
    return Settings(**values)


def _png() -> bytes:
    image = Image.new("RGB", (64, 64), (30, 140, 40))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _run(tmp_path, vision_response):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        assert "tavily" not in str(request.url)
        body = json.loads(request.content.decode())
        if body["model"] == "nvidia/Nemotron-3.5-Super-VL":
            content = body["messages"][1]["content"]
            assert isinstance(content, list)
            assert any(part.get("type") == "image_url" for part in content)
            if isinstance(vision_response, Exception):
                raise vision_response
            return httpx.Response(200, json=vision_response)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "Semana alta. Consulte a su agrónomo."}}],
                "usage": {"prompt_tokens": 4, "completion_tokens": 4, "total_tokens": 8},
            },
        )

    settings = _settings(tmp_path, nebius_api_key="test-key-not-real")
    audit = AuditLog(settings.audit_log)
    client = NebiusClient(settings, audit, transport=httpx.MockTransport(handler))
    result = run_agent(
        settings=settings,
        department="Santa Ana",
        places=places_in("Santa Ana"),
        source=FixtureSource(synthetic_forecast()),
        image=_png(),
        media_type="image/png",
        question=None,
        audit=audit,
        client=client,
        alerts=AlertSearch(settings, audit),
    )
    return result, audit, seen


def _panel(result):
    step = result.steps[2]
    assert step.id == "diagnostico"
    detail = step.detail
    assert detail["orientation_tag"] == ORIENTATION_TAG
    assert detail["consult_label"] == CONSULT_LABEL
    assert detail["consult_href"].startswith("https://wa.me/?text=")
    assert "confidence" not in detail
    for word in ("Seguro", "Probable", "No seguro", "confianza"):
        assert word not in step.farmer_text
    assert "%" not in step.farmer_text
    assert TAG_TAIL not in detail["trust_sentence"]
    return step


def test_nemotron_answer_uses_the_nemotron_line(tmp_path):
    payload = {
        "choices": [
            {
                "message": {
                    "content": '{"label":"roya","confidence":0.93,"retake_reason":null}',
                }
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }
    result, audit, seen = _run(tmp_path, payload)
    step = _panel(result)
    assert step.detail["path"] == "vision"
    assert step.detail["trust_sentence"] == NEMOTRON_TRUST_SENTENCE
    assert step.model_id == "nvidia/Nemotron-3.5-Super-VL"
    assert step.mock is False
    assert any("api.tokenfactory.nebius.com" in url for url in seen)
    assert not any("tavily" in url for url in seen)
    logged = [record for record in audit.records if record["step"] == "diagnostico"]
    assert logged[-1]["path"] == "vision"
    assert logged[-1]["model_id"] == "nvidia/Nemotron-3.5-Super-VL"
    assert "test-key-not-real" not in (tmp_path / "audit.jsonl").read_text(encoding="utf-8")


def test_colour_fallback_uses_the_colour_line(tmp_path):
    result, audit, seen = _run(tmp_path, httpx.ReadTimeout("vision timeout"))
    step = _panel(result)
    assert step.detail["path"] == "colour-lr"
    assert step.detail["trust_sentence"] == COLOUR_TRUST_SENTENCE
    assert step.detail["label"] == "sana"
    assert step.model_id == "colour-histogram-baseline"
    assert "89%" not in step.detail["trust_sentence"]
    assert result.steps[3].detail["decision"]["plan_allowed"] is False
    assert any("api.tokenfactory.nebius.com" in url for url in seen)
    logged = [record for record in audit.records if record["step"] == "diagnostico"]
    assert logged[-1]["path"] == "colour-lr"
    assert logged[-1]["model_id"] == "colour-histogram-baseline"
