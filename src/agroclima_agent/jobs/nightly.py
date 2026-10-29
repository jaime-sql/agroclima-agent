"""Recompute the per-department rust map from Open-Meteo.

Run nightly as a Nebius Serverless AI job. The scorer is the deterministic
rules engine. This module does not read NEBIUS_API_KEY, does not call a model,
and does not call Tavily. Alert refresh is a separate command.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from agroclima_agent.config import load_settings
from agroclima_agent.open_meteo import FixtureSource, ForecastError, ForecastSource, OpenMeteoSource
from agroclima_agent.places import Place, load_places
from agroclima_agent.risk import RISK_FOOTER, synthetic_forecast, worst_level, assess_forecast


def build_map(source: ForecastSource, places: tuple[Place, ...] | list[Place]) -> dict:
    by_department: dict[str, list[dict]] = {}
    for place in places:
        try:
            forecast = source.fetch(place)
            week = assess_forecast(forecast)
            error = None
        except ForecastError as exc:
            week = assess_forecast(None)
            error = str(exc)
        worst = worst_level([day.level for day in week.days]) if week.available else None
        by_department.setdefault(place.department, []).append(
            {
                "id": place.id,
                "name": place.name,
                "available": week.available,
                "worst": worst,
                "days": [
                    {"date": day.date, "level": day.level, "score": day.score}
                    for day in week.days
                ],
                "error": error,
            }
        )
    departments = []
    for name in sorted(by_department):
        rows = by_department[name]
        departments.append(
            {
                "department": name,
                "worst": worst_level([row["worst"] for row in rows]),
                "places": rows,
            }
        )
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "timezone": "America/El_Salvador",
        "source": "open-meteo",
        "model": None,
        "footer": RISK_FOOTER,
        "departments": departments,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Recompute the AgroClima department risk map")
    parser.add_argument("--output", default="var/risk-map.json")
    parser.add_argument(
        "--fixture",
        action="store_true",
        help="Score a built-in forecast instead of calling Open-Meteo",
    )
    args = parser.parse_args()
    source: ForecastSource
    if args.fixture:
        source = FixtureSource(synthetic_forecast())
    else:
        source = OpenMeteoSource(load_settings())
    payload = build_map(source, load_places())
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = ", ".join(
        f"{row['department']}={row['worst'] or 'sin datos'}" for row in payload["departments"]
    )
    print(f"wrote {destination} ({len(payload['departments'])} departments): {summary}")
