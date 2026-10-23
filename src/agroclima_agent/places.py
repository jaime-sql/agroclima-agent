"""Coffee municipalities carried over from AgroClima. Town centres, not farms."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class Place:
    id: str
    name: str
    department: str
    lat: float
    lon: float
    elevation_m: float | None
    coord_type: str
    source: str


def _data_path() -> Path:
    return Path(__file__).resolve().parent / "data" / "locations.json"


@lru_cache(maxsize=1)
def load_places() -> tuple[Place, ...]:
    raw = json.loads(_data_path().read_text(encoding="utf-8"))
    places: list[Place] = []
    for row in raw:
        places.append(
            Place(
                id=row["id"],
                name=row["name"],
                department=row["department"],
                lat=float(row["lat"]),
                lon=float(row["lon"]),
                elevation_m=None if row.get("elevation_m") is None else float(row["elevation_m"]),
                coord_type=row["coord_type"],
                source=row["source"],
            )
        )
    return tuple(places)


def departments() -> list[str]:
    return sorted({place.department for place in load_places()})


def places_in(department: str) -> list[Place]:
    return [place for place in load_places() if place.department == department]
