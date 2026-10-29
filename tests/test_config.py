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


def test_env_example_lists_secrets_without_values():
    text = open(".env.example", encoding="utf-8").read()
    for name in (
        "NEBIUS_API_KEY=",
        "TAVILY_API_KEY=",
        "NEBIUS_BASE_URL=",
        "NEBIUS_MODEL_NANO=",
        "TAVILY_DAILY_CAP=40",
        "TAVILY_TOTAL_CAP=300",
    ):
        assert name in text
    assert "sk-" not in text
    assert "tvly-" not in text
