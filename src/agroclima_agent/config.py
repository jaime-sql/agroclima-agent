"""Environment-only settings. Missing keys select labelled mock mode."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_BASE_URL = "https://api.tokenfactory.nebius.com/v1"
DEFAULT_NANO = "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"
DEFAULT_PLAN = "nvidia/nemotron-3-super-120b-a12b"
DEFAULT_VISION = "nvidia/Nemotron-3.5-Super-VL"
DEFAULT_OPEN_METEO = "https://api.open-meteo.com/v1/forecast"


def _blank(name: str) -> str | None:
    value = os.environ.get(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


@dataclass(frozen=True)
class Settings:
    nebius_api_key: str | None
    nebius_base_url: str
    tavily_api_key: str | None
    model_nano: str
    model_plan: str
    model_vision: str
    audit_log: Path
    host: str
    port: int
    open_meteo_base_url: str

    @property
    def nebius_configured(self) -> bool:
        return self.nebius_api_key is not None

    @property
    def tavily_configured(self) -> bool:
        return self.tavily_api_key is not None

    @property
    def mock(self) -> bool:
        return not self.nebius_configured or not self.tavily_configured

    def mock_reasons(self) -> list[str]:
        reasons: list[str] = []
        if not self.nebius_configured:
            reasons.append("NEBIUS_API_KEY is not set")
        if not self.tavily_configured:
            reasons.append("TAVILY_API_KEY is not set")
        return reasons


def load_settings() -> Settings:
    port_raw = _blank("AGROCLIMA_PORT") or "8000"
    try:
        port = int(port_raw)
    except ValueError:
        port = 8000
    return Settings(
        nebius_api_key=_blank("NEBIUS_API_KEY"),
        nebius_base_url=(_blank("NEBIUS_BASE_URL") or DEFAULT_BASE_URL).rstrip("/"),
        tavily_api_key=_blank("TAVILY_API_KEY"),
        model_nano=_blank("NEBIUS_MODEL_NANO") or DEFAULT_NANO,
        model_plan=_blank("NEBIUS_MODEL_PLAN") or DEFAULT_PLAN,
        model_vision=_blank("NEBIUS_MODEL_VISION") or DEFAULT_VISION,
        audit_log=Path(_blank("AGROCLIMA_AUDIT_LOG") or "var/audit.jsonl"),
        host=_blank("AGROCLIMA_HOST") or "127.0.0.1",
        port=port,
        open_meteo_base_url=(_blank("OPEN_METEO_BASE_URL") or DEFAULT_OPEN_METEO).rstrip("/"),
    )
