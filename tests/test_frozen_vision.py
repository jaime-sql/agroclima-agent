"""The leaf call must send the sealed frozen_config.json bytes."""

import hashlib
import json
from io import BytesIO

import httpx
from PIL import Image

from agroclima_agent.alerts import AlertSearch
from agroclima_agent.audit import AuditLog
from agroclima_agent.config import Settings
from agroclima_agent.frozen_vision import frozen_config_path, load_frozen_vision
from agroclima_agent.nebius import NebiusClient
from agroclima_agent.open_meteo import FixtureSource
from agroclima_agent.pipeline import run_agent
from agroclima_agent.places import places_in
from agroclima_agent.risk import synthetic_forecast

FROZEN_SHA256 = "d0c2017aef15870923f5323298bcec04e8ffa35b7d7634d4c01f8c62959a5f87"


def test_frozen_config_sha256_matches_the_sealed_file():
    raw = frozen_config_path().read_bytes()
    assert hashlib.sha256(raw).hexdigest() == FROZEN_SHA256
    frozen = load_frozen_vision()
    assert frozen["prompt_version"] == "v1"
    assert frozen["temperature"] == 0
    assert frozen["max_tokens"] == 200
    assert "enable_thinking=false" in str(frozen["reasoning"]).replace(" ", "")


def test_vision_request_uses_the_frozen_prompt_verbatim(tmp_path):
    frozen = load_frozen_vision()
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        if body["model"] == frozen["model"]:
            seen["vision"] = body
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {"message": {"content": '{"label":"sana","confidence":0.9}'}}
                    ],
                    "usage": {"prompt_tokens": 4, "completion_tokens": 4, "total_tokens": 8},
                },
            )
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "Semana alta. Consulte a su agrónomo."}}],
                "usage": {"prompt_tokens": 4, "completion_tokens": 4, "total_tokens": 8},
            },
        )

    image = Image.new("RGB", (64, 64), (30, 140, 40))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    settings = Settings(
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
    audit = AuditLog(settings.audit_log)
    client = NebiusClient(settings, audit, transport=httpx.MockTransport(handler))
    run_agent(
        settings=settings,
        department="Santa Ana",
        places=places_in("Santa Ana"),
        source=FixtureSource(synthetic_forecast()),
        image=buffer.getvalue(),
        media_type="image/png",
        question=None,
        audit=audit,
        client=client,
        alerts=AlertSearch(settings, audit),
    )
    body = seen["vision"]
    assert body["temperature"] == 0
    assert body["max_tokens"] == 200
    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    assert body["model"] == frozen["model"]
    assert [message["role"] for message in body["messages"]] == ["user"]
    sent = body["messages"][0]["content"][0]["text"]
    assert sent == frozen["prompt"]
