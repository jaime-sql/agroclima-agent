"""Nano must not show reasoning or internal decision fields to the farmer."""

import json

import httpx

from agroclima_agent.alerts import AlertSearch
from agroclima_agent.audit import AuditLog
from agroclima_agent.config import Settings
from agroclima_agent.nebius import NANO_MAX_TOKENS, NebiusClient
from agroclima_agent.open_meteo import FixtureSource
from agroclima_agent.pipeline import QUESTION_FALLBACK, run_agent
from agroclima_agent.places import places_in
from agroclima_agent.risk import synthetic_forecast

QUESTION = "¿Cómo sigue la semana?"


def _settings(tmp_path):
    return Settings(
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
    )


def _user_text(body: dict) -> str:
    content = body["messages"][-1]["content"]
    if isinstance(content, str):
        return content
    return "\n".join(
        part.get("text", "") for part in content if isinstance(part, dict)
    )


def _response(message: dict) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [{"message": message}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 1848, "total_tokens": 1860},
        },
    )


def _run(tmp_path, question_message: dict, clima_text: str | None = None):
    settings = _settings(tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        assert "tavily" not in str(request.url)
        body = json.loads(request.content.decode())
        text = _user_text(body)
        if body["model"] == settings.model_nano:
            assert body["max_tokens"] == NANO_MAX_TOKENS
            assert body["chat_template_kwargs"] == {"enable_thinking": False}
        if "Pregunta del caficultor" in text:
            assert "Handoff:" not in text
            assert "Nivel decidido" not in text
            return _response(question_message)
        if text.startswith("Escriba en español"):
            assert "Nivel decidido" not in text
            assert "según el pronóstico" in text
            assert "usted ha decidido" not in text.lower()
            spoken = clima_text or "El riesgo de roya en Santa Ana es alto según el pronóstico."
            return _response({"content": spoken})
        return _response({"content": "Semana alta. Consulte a su agrónomo."})

    audit = AuditLog(settings.audit_log)
    client = NebiusClient(settings, audit, transport=httpx.MockTransport(handler))
    return run_agent(
        settings=settings,
        department="Santa Ana",
        places=places_in("Santa Ana"),
        source=FixtureSource(synthetic_forecast()),
        image=None,
        media_type=None,
        question=QUESTION,
        audit=audit,
        client=client,
        alerts=AlertSearch(settings, audit),
    )


def _farmer_blob(result) -> str:
    return "\n".join(step.farmer_text for step in result.steps)


def test_reasoning_only_reply_falls_back_to_the_technician_line(tmp_path):
    reasoning = "Handoff: True. Nivel decidido: alto. " * 40
    result = _run(
        tmp_path,
        {"content": "", "reasoning_content": reasoning},
    )
    blob = _farmer_blob(result)
    assert "Handoff:" not in blob
    assert "Nivel decidido" not in blob
    assert reasoning not in blob
    assert QUESTION_FALLBACK in result.steps[3].farmer_text
    assert "Consultar a un técnico" in result.steps[3].farmer_text


def test_think_tag_reasoning_is_not_shown(tmp_path):
    result = _run(
        tmp_path,
        {"content": "<think>Handoff: True. Nivel decidido: alto.</think>"},
    )
    blob = _farmer_blob(result)
    assert "Handoff:" not in blob
    assert "Nivel decidido" not in blob
    assert QUESTION_FALLBACK in result.steps[3].farmer_text


def test_empty_reply_falls_back_to_the_technician_line(tmp_path):
    result = _run(tmp_path, {"content": None})
    blob = _farmer_blob(result)
    assert "Handoff:" not in blob
    assert "Nivel decidido" not in blob
    assert QUESTION_FALLBACK in result.steps[3].farmer_text


def test_echoed_internal_fields_never_reach_the_farmer(tmp_path):
    result = _run(
        tmp_path,
        {"content": "Nivel decidido: alto. Handoff: True."},
    )
    blob = _farmer_blob(result)
    assert "Handoff:" not in blob
    assert "Nivel decidido" not in blob
    assert QUESTION_FALLBACK in result.steps[3].farmer_text


def test_clima_summary_does_not_say_the_farmer_decided(tmp_path):
    result = _run(
        tmp_path,
        {"content": "La semana sigue con riesgo alto según el pronóstico."},
        clima_text="Usted ha decidido que el nivel de roya en Santa Ana es alto",
    )
    clima = result.steps[0].farmer_text
    assert "según el pronóstico" in clima
    assert "usted ha decidido" not in clima.lower()
    assert "Handoff:" not in _farmer_blob(result)
    assert "Nivel decidido" not in _farmer_blob(result)
