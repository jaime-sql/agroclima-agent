from pathlib import Path

from agroclima_agent.config import (
    DEFAULT_NANO,
    DEFAULT_PLAN,
    DEFAULT_TAVILY_DAILY_CAP,
    DEFAULT_TAVILY_TOTAL_CAP,
    DEFAULT_VISION,
    load_settings,
)


def test_defaults_are_nvidia_models_and_blank_keys_are_mock(monkeypatch):
    for name in (
        "NEBIUS_API_KEY",
        "TAVILY_API_KEY",
        "NEBIUS_BASE_URL",
        "NEBIUS_MODEL_NANO",
        "NEBIUS_MODEL_PLAN",
        "NEBIUS_MODEL_VISION",
    ):
        monkeypatch.delenv(name, raising=False)
    settings = load_settings()
    assert settings.mock is True
    assert settings.model_nano == DEFAULT_NANO
    assert settings.model_plan == DEFAULT_PLAN
    assert settings.model_vision == DEFAULT_VISION
    assert settings.nebius_base_url == "https://api.tokenfactory.nebius.com/v1"
    assert settings.tavily_daily_cap == DEFAULT_TAVILY_DAILY_CAP == 40
    assert settings.tavily_total_cap == DEFAULT_TAVILY_TOTAL_CAP == 300
    assert all(model.startswith("nvidia/") for model in (
        settings.model_nano,
        settings.model_plan,
        settings.model_vision,
    ))


def test_plan_model_can_switch_to_ultra(monkeypatch):
    monkeypatch.setenv("NEBIUS_MODEL_PLAN", "nvidia/Nemotron-3-Ultra-550b-a55b")
    monkeypatch.setenv("NEBIUS_API_KEY", "  ")
    monkeypatch.setenv("TAVILY_API_KEY", "")
    settings = load_settings()
    assert settings.model_plan == "nvidia/Nemotron-3-Ultra-550b-a55b"
    assert settings.nebius_configured is False
    assert settings.tavily_configured is False


def test_cloud_run_port_wins_and_opens_the_host(monkeypatch):
    monkeypatch.setenv("PORT", "8080")
    monkeypatch.setenv("AGROCLIMA_PORT", "8000")
    monkeypatch.delenv("AGROCLIMA_HOST", raising=False)
    settings = load_settings()
    assert settings.port == 8080
    assert settings.host == "0.0.0.0"


def test_explicit_host_is_kept_when_cloud_run_sets_port(monkeypatch):
    monkeypatch.setenv("PORT", "8080")
    monkeypatch.setenv("AGROCLIMA_HOST", "0.0.0.0")
    settings = load_settings()
    assert settings.port == 8080
    assert settings.host == "0.0.0.0"


def test_local_port_and_host_without_cloud_run_port(monkeypatch):
    monkeypatch.delenv("PORT", raising=False)
    monkeypatch.setenv("AGROCLIMA_PORT", "9000")
    monkeypatch.setenv("AGROCLIMA_HOST", "127.0.0.1")
    settings = load_settings()
    assert settings.port == 9000
    assert settings.host == "127.0.0.1"


def test_invalid_cloud_run_port_uses_agroclima_port(monkeypatch):
    monkeypatch.setenv("PORT", "nope")
    monkeypatch.setenv("AGROCLIMA_PORT", "8000")
    settings = load_settings()
    assert settings.port == 8000


def test_local_var_paths_stay_under_var(monkeypatch):
    monkeypatch.delenv("VERCEL", raising=False)
    for name in ("AGROCLIMA_AUDIT_LOG", "AGROCLIMA_TAVILY_CACHE", "AGROCLIMA_TAVILY_COUNTER"):
        monkeypatch.delenv(name, raising=False)
    settings = load_settings()
    assert settings.audit_log == Path("var/audit.jsonl")
    assert settings.tavily_cache_path == Path("var/tavily-cache.json")
    assert settings.tavily_counter_path == Path("var/tavily-usage.json")


def test_vercel_writes_var_paths_to_tmp(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    for name in ("AGROCLIMA_AUDIT_LOG", "AGROCLIMA_TAVILY_CACHE", "AGROCLIMA_TAVILY_COUNTER"):
        monkeypatch.delenv(name, raising=False)
    settings = load_settings()
    assert settings.audit_log == Path("/tmp/audit.jsonl")
    assert settings.tavily_cache_path == Path("/tmp/tavily-cache.json")
    assert settings.tavily_counter_path == Path("/tmp/tavily-usage.json")


def test_explicit_paths_win_on_vercel(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("AGROCLIMA_AUDIT_LOG", "var/custom.jsonl")
    settings = load_settings()
    assert settings.audit_log == Path("var/custom.jsonl")


def test_env_example_lists_secrets_without_values():
    text = open(".env.example", encoding="utf-8").read()
    for name in (
        "NEBIUS_API_KEY=",
        "TAVILY_API_KEY=",
        "NEBIUS_BASE_URL=",
        "NEBIUS_MODEL_NANO=",
        "TAVILY_DAILY_CAP=40",
        "TAVILY_TOTAL_CAP=300",
        "AGROCLIMA_DAILY_RUN_CAP=300",
    ):
        assert name in text
    assert "sk-" not in text
    assert "tvly-" not in text
