import json
from datetime import datetime, timedelta, timezone

import httpx

from agroclima_agent.alerts import SEARCH_DEPTH, AlertSearch, basic_search_body
from agroclima_agent.audit import AuditLog, tavily_usage
from agroclima_agent.config import Settings
from agroclima_agent.jobs import nightly, refresh_alerts
from agroclima_agent.web.app import create_app
from agroclima_agent.open_meteo import FixtureSource
from agroclima_agent.risk import synthetic_forecast
from fastapi.testclient import TestClient
import inspect


def _settings(tmp_path, **overrides):
    values = dict(
        nebius_api_key=None,
        nebius_base_url="https://api.tokenfactory.nebius.com/v1",
        tavily_api_key="tavily-test",
        model_nano="nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B",
        model_plan="nvidia/nemotron-3-super-120b-a12b",
        model_vision="nvidia/Nemotron-3.5-Super-VL",
        audit_log=tmp_path / "audit.jsonl",
        host="127.0.0.1",
        port=8000,
        open_meteo_base_url="https://api.open-meteo.com/v1/forecast",
        tavily_daily_cap=40,
        tavily_total_cap=300,
        tavily_cache_path=tmp_path / "cache.json",
        tavily_counter_path=tmp_path / "counter.json",
    )
    values.update(overrides)
    return Settings(**values)


def _clock(start):
    state = {"now": start}

    def current():
        return state["now"]

    return state, current


def _ok(request: httpx.Request) -> httpx.Response:
    assert str(request.url) == "https://api.tavily.com/search"
    body = json.loads(request.content.decode())
    assert body == basic_search_body("Santa Ana") or body["search_depth"] == "basic"
    assert body["search_depth"] == SEARCH_DEPTH == "basic"
    assert body["max_results"] <= 5
    assert "extract" not in str(request.url)
    return httpx.Response(
        200,
        json={
            "results": [
                {
                    "title": "Boletín CENTA",
                    "url": "https://www.centa.gob.sv/roya",
                    "content": "Vigilancia de roya en el país.",
                }
            ]
        },
    )


def test_page_load_never_calls_tavily_and_refresh_is_once_per_day(tmp_path):
    start = datetime(2026, 10, 23, 12, tzinfo=timezone.utc)
    state, clock = _clock(start)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return _ok(request)

    settings = _settings(tmp_path)
    audit = AuditLog(settings.audit_log)
    search = AlertSearch(settings, audit, transport=httpx.MockTransport(handler), clock=clock)
    assert search.search("Santa Ana")[0].stale is True
    assert calls["n"] == 0

    first = search.refresh("Santa Ana")
    assert calls["n"] == 1
    assert first[0].stale is False
    assert first[0].official is True

    state["now"] = start + timedelta(hours=23)
    search.refresh("Santa Ana")
    served = search.search("Santa Ana")
    assert calls["n"] == 1
    assert served[0].title == "Boletín CENTA"
    assert served[0].stale is False

    state["now"] = start + timedelta(hours=25)
    search.refresh("Santa Ana")
    assert calls["n"] == 2

    usage = tavily_usage(settings.audit_log)
    assert usage == {"count": 2, "credits": 2}
    counter = json.loads(settings.tavily_counter_path.read_text(encoding="utf-8"))
    assert counter["total"] == 2
    logged = settings.audit_log.read_text(encoding="utf-8")
    assert "tavily-test" not in logged


def test_cap_returns_last_known_without_calling(tmp_path):
    start = datetime(2026, 10, 23, 15, tzinfo=timezone.utc)
    state, clock = _clock(start)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return _ok(request)

    settings = _settings(tmp_path, tavily_total_cap=1, tavily_daily_cap=40)
    audit = AuditLog(settings.audit_log)
    search = AlertSearch(settings, audit, transport=httpx.MockTransport(handler), clock=clock)
    search.refresh("Santa Ana")
    assert calls["n"] == 1

    state["now"] = start + timedelta(hours=25)
    blocked = search.refresh("Santa Ana")
    assert calls["n"] == 1
    assert blocked[0].stale is True
    assert blocked[0].snippet.lower().startswith("sin actualizar")
    assert tavily_usage(settings.audit_log) == {"count": 1, "credits": 1}


def test_daily_cap_resets_on_the_el_salvador_day(tmp_path):
    # 06:00 UTC is 00:00 in El Salvador (UTC-6, no DST).
    start = datetime(2026, 10, 23, 6, tzinfo=timezone.utc)
    state, clock = _clock(start)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return _ok(request)

    settings = _settings(tmp_path, tavily_daily_cap=1, tavily_total_cap=300)
    search = AlertSearch(
        settings,
        AuditLog(settings.audit_log),
        transport=httpx.MockTransport(handler),
        clock=clock,
    )
    search.refresh("Santa Ana")
    state["now"] = start + timedelta(hours=2)
    search.refresh("Ahuachapán")
    assert calls["n"] == 1
    state["now"] = start + timedelta(days=1)
    search.refresh("Ahuachapán")
    assert calls["n"] == 2


def test_usage_endpoint_reads_only_tavily_search_lines(tmp_path):
    settings = _settings(tmp_path, tavily_api_key=None)
    settings.audit_log.write_text(
        "\n".join(
            [
                json.dumps({"step": "alertas", "credits": 0, "mock": True}),
                json.dumps({"step": "tavily-search", "credits": 1, "mock": False}),
                json.dumps({"step": "plan", "credits": None, "mock": True}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    client = TestClient(create_app(settings, FixtureSource(synthetic_forecast())))
    assert client.get("/api/tavily-usage").json() == {"count": 1, "credits": 1}
    assert "search_depth" not in inspect.getsource(refresh_alerts)
    assert "api.tavily.com" not in inspect.getsource(nightly)
