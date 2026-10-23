"""Deterministic Hemileia vastatrix weather rules.

The recipe is the one in docs/rust-risk-rules.md (AgroClima v1). A model
must not change these cutoffs or the level of a day.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

REASON_ALTO = "«Hojas mojadas muchas horas y clima tibio: la roya se pega fácil.»"
REASON_MEDIO = "«Humedad o lluvia algunas horas: riesgo moderado.»"
REASON_BAJO_SECO = "«Día seco: la roya casi no avanza.»"
REASON_BAJO_TEMP = "«Temperatura poco favorable para la roya.»"
REASON_BAJO_POCAS = "«Pocas horas húmedas favorables; riesgo bajo de roya»"
REASON_BAJO_LLUVIA = "«Llueve, pero sin horas húmedas favorables a la roya»"
REASON_SIN_DATOS = "«sin datos»"
FORECAST_UNAVAILABLE = "«pronóstico no disponible»"
RISK_FOOTER = (
    "Estos umbrales de riesgo son una estimación nuestra y no han sido "
    "validados por el ISC, CENTA ni el MAG."
)
DOSE_NOTE = "dosis según etiqueta / su agrónomo"
FUNGICIDE_CLASSES = ("cobre", "triazol", "triazol+estrobilurina")
TIMEZONE = "America/El_Salvador"
LEVEL_RANK = {"bajo": 1, "medio": 2, "alto": 3}


def display_reason(reason: str) -> str:
    return reason.strip("«»").strip()


@dataclass
class SprayWindow:
    start: str
    end: str


@dataclass
class DayAssessment:
    date: str
    level: str | None
    reason: str
    score: int
    wet_hours: int | None
    tmax: float | None
    rain: float | None
    warm_wet_hours: int
    opt_wet_hours: int
    rain_day: bool
    latency_band: bool
    consecutive_bonus: bool


@dataclass
class WeekAssessment:
    available: bool
    timezone: str | None
    days: list[DayAssessment] = field(default_factory=list)
    footer: str = RISK_FOOTER
    message: str = ""


def _finite(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value != value or value in (float("inf"), float("-inf")):
        return None
    return float(value)


def _previous_date(iso_date: str) -> str | None:
    try:
        year, month, day = (int(part) for part in iso_date.split("-"))
        return (date(year, month, day) - timedelta(days=1)).isoformat()
    except ValueError:
        return None


def _hour_rows(hourly: dict) -> list[dict]:
    count = len(hourly.get("time") or [])
    rows = []
    for index in range(count):
        rows.append(
            {
                "time": hourly["time"][index],
                "temperature_2m": _finite(hourly["temperature_2m"][index]),
                "relative_humidity_2m": _finite(hourly["relative_humidity_2m"][index]),
                "precipitation": _finite(hourly["precipitation"][index]),
                "precipitation_probability": _finite(
                    (hourly.get("precipitation_probability") or [None] * count)[index]
                ),
            }
        )
    rows.sort(key=lambda row: row["time"])
    return rows


def _is_wet(hour: dict) -> bool:
    humid = hour["relative_humidity_2m"] is not None and hour["relative_humidity_2m"] >= 90
    rain = hour["precipitation"] is not None and hour["precipitation"] >= 0.1
    return humid or rain


def _is_dry_spray(hour: dict) -> bool:
    return (
        hour["precipitation"] is not None
        and hour["precipitation"] < 0.1
        and hour["precipitation_probability"] is not None
        and hour["precipitation_probability"] < 40
        and hour["relative_humidity_2m"] is not None
        and hour["relative_humidity_2m"] < 90
    )


def _next_stamp(stamp: str) -> str | None:
    if len(stamp) < 13 or stamp[10] != "T":
        return None
    try:
        year = int(stamp[0:4])
        month = int(stamp[5:7])
        day = int(stamp[8:10])
        hour = int(stamp[11:13])
    except ValueError:
        return None
    nxt = date(year, month, day)
    hour += 1
    if hour >= 24:
        hour = 0
        nxt = nxt + timedelta(days=1)
    return f"{nxt.isoformat()}T{hour:02d}:00"


def next_dry_spray_window(hourly: dict | None) -> SprayWindow | None:
    if not hourly:
        return None
    rows = _hour_rows(hourly)
    for start in range(0, len(rows) - 3):
        ok = True
        for offset in range(4):
            if not _is_dry_spray(rows[start + offset]):
                ok = False
                break
            if offset > 0:
                expected = _next_stamp(rows[start + offset - 1]["time"])
                actual = rows[start + offset]["time"][:16]
                if expected is None or actual != expected:
                    ok = False
                    break
        if ok:
            return SprayWindow(start=rows[start]["time"], end=rows[start + 3]["time"])
    return None


def _forecast_usable(forecast: dict) -> bool:
    if forecast.get("timezone") != TIMEZONE:
        return False
    hourly = forecast.get("hourly") or {}
    daily = forecast.get("daily") or {}
    if not hourly.get("time") or not daily.get("time"):
        return False
    for key in ("temperature_2m", "relative_humidity_2m", "precipitation"):
        if not isinstance(hourly.get(key), list):
            return False
    for key in ("temperature_2m_max", "precipitation_sum", "precipitation_probability_max"):
        if not isinstance(daily.get(key), list):
            return False
    return True


def _complete_day(rows: list[dict], day: str) -> list[dict] | None:
    by_hour = {row["time"][11:13]: row for row in rows if str(row["time"]).startswith(day)}
    ordered = []
    for hour in range(24):
        row = by_hour.get(f"{hour:02d}")
        if row is None:
            return None
        if (
            row["temperature_2m"] is None
            or row["relative_humidity_2m"] is None
            or row["precipitation"] is None
        ):
            return None
        ordered.append(row)
    return ordered


def _missing(day: str) -> DayAssessment:
    return DayAssessment(
        date=day,
        level=None,
        reason=REASON_SIN_DATOS,
        score=0,
        wet_hours=None,
        tmax=None,
        rain=None,
        warm_wet_hours=0,
        opt_wet_hours=0,
        rain_day=False,
        latency_band=False,
        consecutive_bonus=False,
    )


def _reason(level: str, wet_hours: int, warm_wet: int, precipitation_sum: float | None) -> str:
    if level == "bajo":
        if wet_hours == 0 and precipitation_sum is not None and precipitation_sum >= 1:
            return REASON_BAJO_LLUVIA
        if wet_hours == 0:
            return REASON_BAJO_SECO
        if warm_wet == 0:
            return REASON_BAJO_TEMP
        return REASON_BAJO_POCAS
    if level == "alto":
        return REASON_ALTO
    return REASON_MEDIO


def assess_forecast(forecast: dict | None) -> WeekAssessment:
    if not forecast or not _forecast_usable(forecast):
        return WeekAssessment(
            available=False,
            timezone=None,
            message=FORECAST_UNAVAILABLE,
        )
    hourly = forecast["hourly"]
    daily = forecast["daily"]
    hours = _hour_rows(hourly)
    order = sorted(enumerate(daily["time"]), key=lambda item: item[1])
    measured = []
    for index, day in order:
        day_hours = _complete_day(hours, day)
        precip_sum = _finite(_at(daily["precipitation_sum"], index))
        prob_max = _finite(_at(daily["precipitation_probability_max"], index))
        tmax = _finite(_at(daily["temperature_2m_max"], index))
        if day_hours is None or precip_sum is None or prob_max is None or tmax is None:
            measured.append({"date": day, "incomplete": True})
            continue
        wet_hours = 0
        warm_wet = 0
        opt_wet = 0
        rain = 0.0
        for hour in day_hours:
            if hour["precipitation"] is not None:
                rain += hour["precipitation"]
            if not _is_wet(hour):
                continue
            wet_hours += 1
            temperature = hour["temperature_2m"]
            if temperature is None or temperature < 15 or temperature > 30:
                continue
            warm_wet += 1
            if 21 <= temperature <= 25:
                opt_wet += 1
        measured.append(
            {
                "date": day,
                "incomplete": False,
                "wet_hours": wet_hours,
                "warm_wet": warm_wet,
                "opt_wet": opt_wet,
                "rain_day": precip_sum >= 1 or prob_max >= 60,
                "precip_sum": precip_sum,
                "tmax": tmax,
                "rain": rain,
                "latency": 22 <= tmax <= 28,
            }
        )
    warm_by_date = {
        row["date"]: None if row["incomplete"] else row["warm_wet"] for row in measured
    }
    days: list[DayAssessment] = []
    for row in measured:
        if row["incomplete"]:
            days.append(_missing(row["date"]))
            continue
        previous = _previous_date(row["date"])
        previous_warm = warm_by_date.get(previous) if previous else None
        bonus = row["warm_wet"] >= 6 and previous_warm is not None and previous_warm >= 6
        score = 0
        if row["warm_wet"] >= 6:
            score += 2
        elif row["warm_wet"] >= 3:
            score += 1
        if row["opt_wet"] >= 3:
            score += 1
        if row["rain_day"]:
            score += 1
        if row["latency"]:
            score += 1
        if bonus:
            score += 1
        if row["wet_hours"] == 0 or row["warm_wet"] == 0:
            level = "bajo"
        elif score >= 4:
            level = "alto"
        elif score >= 2:
            level = "medio"
        else:
            level = "bajo"
        days.append(
            DayAssessment(
                date=row["date"],
                level=level,
                reason=_reason(level, row["wet_hours"], row["warm_wet"], row["precip_sum"]),
                score=score,
                wet_hours=row["wet_hours"],
                tmax=row["tmax"],
                rain=row["rain"],
                warm_wet_hours=row["warm_wet"],
                opt_wet_hours=row["opt_wet"],
                rain_day=row["rain_day"],
                latency_band=row["latency"],
                consecutive_bonus=bonus,
            )
        )
    return WeekAssessment(available=True, timezone=TIMEZONE, days=days)


def _at(values: list, index: int) -> object:
    if index >= len(values):
        return None
    return values[index]


def worst_level(levels: list[str | None]) -> str | None:
    present = [level for level in levels if level in LEVEL_RANK]
    if not present:
        return None
    return max(present, key=lambda level: LEVEL_RANK[level])


def synthetic_forecast(
    *,
    start: str = "2026-10-12",
    days: int = 7,
    warm_wet_hours: int = 6,
    temperature: float = 22,
    tmax: float = 24,
    precipitation_sum: float = 2,
    probability_max: float = 70,
) -> dict:
    """A complete America/El_Salvador forecast for tests and the fixture job."""
    year, month, day = (int(part) for part in start.split("-"))
    cursor = date(year, month, day)
    hourly = {
        "time": [],
        "temperature_2m": [],
        "relative_humidity_2m": [],
        "precipitation": [],
        "precipitation_probability": [],
    }
    daily = {
        "time": [],
        "temperature_2m_max": [],
        "temperature_2m_min": [],
        "precipitation_sum": [],
        "precipitation_hours": [],
        "precipitation_probability_max": [],
    }
    for _ in range(days):
        iso = cursor.isoformat()
        daily["time"].append(iso)
        daily["temperature_2m_max"].append(tmax)
        daily["temperature_2m_min"].append(18)
        daily["precipitation_sum"].append(precipitation_sum)
        daily["precipitation_hours"].append(warm_wet_hours)
        daily["precipitation_probability_max"].append(probability_max)
        for hour in range(24):
            wet = hour < warm_wet_hours
            hourly["time"].append(f"{iso}T{hour:02d}:00")
            hourly["temperature_2m"].append(temperature if wet else 20)
            hourly["relative_humidity_2m"].append(95 if wet else 60)
            hourly["precipitation"].append(0.2 if wet else 0)
            hourly["precipitation_probability"].append(10 if hour >= 12 else 80)
        cursor += timedelta(days=1)
    return {"timezone": TIMEZONE, "hourly": hourly, "daily": daily}
