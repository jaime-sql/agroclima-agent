"""In-memory spend guard for the public /api/run endpoint."""

from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Callable
from zoneinfo import ZoneInfo

from fastapi import Request

SV = ZoneInfo("America/El_Salvador")
PER_IP_LIMIT = 10
PER_IP_WINDOW_SECONDS = 10 * 60

MESSAGES = {
    "rate": {
        "es": "Demasiadas consultas desde esta conexión. Espere unos minutos e intente de nuevo.",
        "en": "Too many requests from this connection. Wait a few minutes and try again.",
    },
    "daily": {
        "es": "Por hoy ya no hay consultas disponibles. Vuelva mañana.",
        "en": "No consultations are left for today. Please come back tomorrow.",
    },
    "department": {
        "es": "Departamento desconocido.",
        "en": "Unknown department.",
    },
    "photo_size": {
        "es": "La foto pesa más de 5 MB.",
        "en": "The photo is larger than 5 MB.",
    },
    "photo_type": {
        "es": "La foto debe ser JPEG, PNG o WebP.",
        "en": "The photo must be JPEG, PNG, or WebP.",
    },
    "missing": {
        "es": "Faltan datos de la consulta. Indique el departamento.",
        "en": "The request is missing a department.",
    },
}


def normalize_lang(value: str | None) -> str:
    raw = (value or "").strip().lower()
    return "en" if raw.startswith("en") else "es"


def guard_message(kind: str, language: str | None) -> str:
    return MESSAGES[kind][normalize_lang(language)]


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    real = request.headers.get("x-real-ip", "").strip()
    if real:
        return real
    if request.client is not None and request.client.host:
        return request.client.host
    return "unknown"


def farmer_model_id(model_id: str | None) -> str | None:
    """Model ids the farmer may see. Internal source names stay off the meta line."""
    if model_id and model_id.startswith("nvidia/"):
        return model_id
    return None


class RunGuard:
    """Per-IP sliding window plus one El Salvador daily cap, both in memory."""

    def __init__(
        self,
        *,
        daily_cap: int,
        per_ip: int = PER_IP_LIMIT,
        window_seconds: float = PER_IP_WINDOW_SECONDS,
        clock: Callable[[], float] | None = None,
        today: Callable[[], str] | None = None,
    ) -> None:
        self.daily_cap = daily_cap
        self.per_ip = per_ip
        self.window_seconds = window_seconds
        self._clock = clock or time.monotonic
        self._today = today or _today_sv
        self._hits: dict[str, list[float]] = {}
        self._day: str | None = None
        self._runs = 0
        self._lock = threading.Lock()

    def allow_ip(self, ip: str) -> bool:
        now = self._clock()
        with self._lock:
            hits = [stamp for stamp in self._hits.get(ip, []) if now - stamp < self.window_seconds]
            if len(hits) >= self.per_ip:
                self._hits[ip] = hits
                return False
            hits.append(now)
            self._hits[ip] = hits
            return True

    def allow_daily(self) -> bool:
        today = self._today()
        with self._lock:
            if today != self._day:
                self._day = today
                self._runs = 0
            if self._runs >= self.daily_cap:
                return False
            self._runs += 1
            return True


def _today_sv() -> str:
    return datetime.now(SV).date().isoformat()
