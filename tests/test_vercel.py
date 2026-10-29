import json
from pathlib import Path

from agroclima_agent.web.app import app as web_app


def test_vercel_entrypoint_exports_the_asgi_app():
    from api.index import app

    assert app is web_app
    paths = {route.path for route in app.routes}
    assert "/" in paths
    assert "/api/health" in paths
    assert "/api/run" in paths


def test_vercel_json_configures_the_python_entrypoint():
    config = json.loads(Path("vercel.json").read_text(encoding="utf-8"))
    function = config["functions"]["api/index.py"]
    assert function["maxDuration"] >= 60
    assert "src/**" in function["includeFiles"]
    project = Path("pyproject.toml").read_text(encoding="utf-8")
    assert 'entrypoint = "api.index:app"' in project
