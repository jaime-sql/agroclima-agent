"""Environment-only settings. A missing Nebius key selects labelled mock mode."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_BASE_URL = "https://api.tokenfactory.nebius.com/v1"
DEFAULT_NANO = "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"
DEFAULT_PLAN = "nvidia/nemotron-3-super-120b-a12b"
DEFAULT_VISION = "nvidia/Nemotron-3.5-Super-VL"
DEFAULT_OPEN_METEO = "https://api.open-meteo.com/v1/forecast"
DEFAULT_TAVILY_DAILY_CAP = 40
DEFAULT_TAVILY_TOTAL_CAP = 300


def _blank(name: str) -> str | None:
    value = os.environ.get(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _positive_int(name: str, default: int) -> int:
    raw = _blank(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value >= 0 else default


def _listen_port() -> int:
    """Cloud Run injects PORT. AGROCLIMA_PORT applies when PORT is absent or invalid."""
    for name in ("PORT", "AGROCLIMA_PORT"):
        raw = _blank(name)
        if raw is None:
            continue
        try:
            value = int(raw)
        except ValueError:
            continue
        if 1 <= value <= 65535:
            return value
    return 8000


def _listen_host() -> str:
    """Bind every interface on Cloud Run. Local runs stay on localhost unless overridden."""
    host = _blank("AGROCLIMA_HOST")
    if host is not None:
        return host
    if _blank("PORT"):
        return "0.0.0.0"
    return "127.0.0.1"


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
    tavily_daily_cap: int = DEFAULT_TAVILY_DAILY_CAP
    tavily_total_cap: int = DEFAULT_TAVILY_TOTAL_CAP
    tavily_cache_path: Path = field(default_factory=lambda: Path("var/tavily-cache.json"))
    tavily_counter_path: Path = field(default_factory=lambda: Path("var/tavily-usage.json"))
    technician_whatsapp: str | None = None

    @property
    def nebius_configured(self) -> bool:
        return self.nebius_api_key is not None

    @property
    def tavily_configured(self) -> bool:
        return self.tavily_api_key is not None

    @property
    def mock(self) -> bool:
        """Model mock only. A missing Tavily key does not mock the whole app."""
        return not self.nebius_configured

    def mock_reasons(self) -> list[str]:
        if not self.nebius_configured:
            return ["NEBIUS_API_KEY is not set"]
        return []


def load_settings() -> Settings:
    return Settings(
        nebius_api_key=_blank("NEBIUS_API_KEY"),
        nebius_base_url=(_blank("NEBIUS_BASE_URL") or DEFAULT_BASE_URL).rstrip("/"),
        tavily_api_key=_blank("TAVILY_API_KEY"),
        model_nano=_blank("NEBIUS_MODEL_NANO") or DEFAULT_NANO,
        model_plan=_blank("NEBIUS_MODEL_PLAN") or DEFAULT_PLAN,
        model_vision=_blank("NEBIUS_MODEL_VISION") or DEFAULT_VISION,
        audit_log=Path(_blank("AGROCLIMA_AUDIT_LOG") or "var/audit.jsonl"),
        host=_listen_host(),
        port=_listen_port(),
        open_meteo_base_url=(_blank("OPEN_METEO_BASE_URL") or DEFAULT_OPEN_METEO).rstrip("/"),
        tavily_daily_cap=_positive_int("TAVILY_DAILY_CAP", DEFAULT_TAVILY_DAILY_CAP),
        tavily_total_cap=_positive_int("TAVILY_TOTAL_CAP", DEFAULT_TAVILY_TOTAL_CAP),
        tavily_cache_path=Path(_blank("AGROCLIMA_TAVILY_CACHE") or "var/tavily-cache.json"),
        tavily_counter_path=Path(_blank("AGROCLIMA_TAVILY_COUNTER") or "var/tavily-usage.json"),
        technician_whatsapp=_blank("TECHNICIAN_WHATSAPP"),
    )
