from fastapi.testclient import TestClient
from PIL import Image
from io import BytesIO

from agroclima_agent.config import Settings
from agroclima_agent.open_meteo import FixtureSource
from agroclima_agent.risk import synthetic_forecast
from agroclima_agent.trust_sentences import COLOUR_TRUST_SENTENCE
from agroclima_agent.web.app import create_app


def _settings(tmp_path):
    return Settings(
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
    )


def _png() -> bytes:
    image = Image.new("RGB", (64, 64), (30, 140, 40))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_health_page_and_mock_run(tmp_path):
    app = create_app(_settings(tmp_path), FixtureSource(synthetic_forecast()))
    client = TestClient(app)
    health = client.get("/api/health")
    assert health.status_code == 200
    body = health.json()
    assert body["ok"] is True
    assert body["mock"] is True
    assert body["models"]["nano"].startswith("nvidia/")
    assert body["models"]["plan"].startswith("nvidia/")
    assert body["models"]["vision"].startswith("nvidia/")
    assert "test-key" not in health.text

    page = client.get("/")
    assert page.status_code == 200
    assert "Clima → Alertas oficiales → Diagnóstico → Plan" in page.text
    assert "Mock mode" in page.text
    assert "trust_sentence" in page.text
    assert "orientation_tag" in page.text
    assert "consult_href" in page.text

    departments = client.get("/api/departments").json()["departments"]
    assert "Santa Ana" in departments
    assert client.get("/api/tavily-usage").json() == {"count": 0, "credits": 0}

    run = client.post("/api/run", data={"department": "Santa Ana", "question": ""})
    assert run.status_code == 200
    payload = run.json()
    assert [step["id"] for step in payload["steps"]] == ["clima", "alertas", "diagnostico", "plan"]
    assert payload["steps"][0]["detail"]["worst"] == "alto"
    assert payload["steps"][1]["citations"][0]["url"].startswith("https://")
    assert payload["steps"][3]["detail"]["decision"]["handoff_required"] is True
    logged = (tmp_path / "audit.jsonl").read_text(encoding="utf-8")
    assert "sk-" not in logged

    with_photo = client.post(
        "/api/run",
        data={"department": "Usulután"},
        files={"photo": ("leaf.png", _png(), "image/png")},
    )
    assert with_photo.status_code == 200
    diagnosis = with_photo.json()["steps"][2]
    assert diagnosis["mock"] is True
    assert diagnosis["detail"]["path"] == "colour-lr"
    assert diagnosis["detail"]["label"] == "sana"
    assert diagnosis["detail"]["trust_sentence"] == COLOUR_TRUST_SENTENCE
    assert "89%" not in diagnosis["detail"]["trust_sentence"]
    assert "Orientativo" not in diagnosis["detail"]["trust_sentence"]
    assert "fotografiadas sobre fondo blanco, no en el campo" in diagnosis["detail"]["trust_sentence"]
    assert diagnosis["detail"]["orientation_tag"] == "Orientativo — no es un diagnóstico"
    assert diagnosis["detail"]["consult_label"] == "Consultar a un técnico"
    assert diagnosis["detail"]["consult_href"] == "#tecnico"
    assert "wa.me" not in diagnosis["detail"]["consult_href"]
    assert "Seguro" not in diagnosis["farmer_text"]
    assert "%" not in diagnosis["farmer_text"]
    assert with_photo.json()["steps"][3]["detail"]["decision"]["plan_allowed"] is False
    assert "diagnosis_band" not in with_photo.json()["steps"][3]["detail"]["decision"]

    unknown = client.post("/api/run", data={"department": "Narnia"})
    assert unknown.status_code == 400
