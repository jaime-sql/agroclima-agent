"""Open-Meteo forecast client. Coordinates are rounded to 3 decimals."""

from __future__ import annotations

from agroclima_agent.config import Settings
from agroclima_agent.places import Place

import httpx


class ForecastError(Exception):
    pass


class ForecastSource:
    def fetch(self, place: Place) -> dict:
        raise NotImplementedError


class OpenMeteoSource(ForecastSource):
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None) -> None:
        self.settings = settings
        self._transport = transport

    def fetch(self, place: Place) -> dict:
        params = {
            "latitude": f"{place.lat:.3f}",
            "longitude": f"{place.lon:.3f}",
            "hourly": "temperature_2m,relative_humidity_2m,precipitation,precipitation_probability",
            "daily": ",".join(
                [
                    "temperature_2m_max",
                    "temperature_2m_min",
                    "precipitation_sum",
                    "precipitation_hours",
                    "precipitation_probability_max",
                ]
            ),
            "timezone": "America/El_Salvador",
            "forecast_days": 7,
        }
        try:
            with httpx.Client(transport=self._transport, timeout=20) as client:
                response = client.get(self.settings.open_meteo_base_url, params=params)
        except httpx.HTTPError as exc:
            raise ForecastError("transport") from exc
        if response.status_code != 200:
            raise ForecastError(f"http_{response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise ForecastError("bad_json") from exc
        if not isinstance(payload, dict):
            raise ForecastError("bad_json")
        return payload


class FixtureSource(ForecastSource):
    def __init__(self, forecast: dict) -> None:
        self.forecast = forecast

    def fetch(self, place: Place) -> dict:
        return self.forecast
