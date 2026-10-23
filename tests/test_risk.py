from agroclima_agent.risk import (
    REASON_ALTO,
    REASON_BAJO_LLUVIA,
    REASON_BAJO_POCAS,
    REASON_BAJO_SECO,
    REASON_BAJO_TEMP,
    REASON_MEDIO,
    REASON_SIN_DATOS,
    assess_forecast,
    next_dry_spray_window,
    synthetic_forecast,
)


def _forecast(days):
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
    for day in days:
        daily["time"].append(day["date"])
        daily["temperature_2m_max"].append(day.get("tmax", 20))
        daily["temperature_2m_min"].append(18)
        daily["precipitation_sum"].append(day.get("precip_sum", 0))
        daily["precipitation_hours"].append(0)
        daily["precipitation_probability_max"].append(day.get("prob", 0))
        by_hour = {hour["time"][11:13]: hour for hour in day["hours"]}
        for hour in range(24):
            key = f"{hour:02d}"
            row = by_hour.get(key) or {
                "time": f"{day['date']}T{key}:00",
                "temperature_2m": 18,
                "relative_humidity_2m": 60,
                "precipitation": 0,
                "precipitation_probability": 0,
            }
            hourly["time"].append(row["time"])
            hourly["temperature_2m"].append(row.get("temperature_2m", 18))
            hourly["relative_humidity_2m"].append(row.get("relative_humidity_2m", 50))
            hourly["precipitation"].append(row.get("precipitation", 0))
            hourly["precipitation_probability"].append(row.get("precipitation_probability", 0))
    return {"timezone": "America/El_Salvador", "hourly": hourly, "daily": daily}


def _wet(date, count, temperature):
    return [
        {
            "time": f"{date}T{index:02d}:00",
            "temperature_2m": temperature,
            "relative_humidity_2m": 95,
            "precipitation": 0,
            "precipitation_probability": 0,
        }
        for index in range(count)
    ]


def test_optimum_wet_hours_score_and_alto_band():
    optimum = assess_forecast(
        _forecast([{"date": "2026-10-10", "hours": _wet("2026-10-10", 3, 22), "tmax": 20}])
    ).days[0]
    warm = assess_forecast(
        _forecast([{"date": "2026-10-10", "hours": _wet("2026-10-10", 3, 18), "tmax": 20}])
    ).days[0]
    assert optimum.opt_wet_hours == 3
    assert optimum.score == 2
    assert optimum.level == "medio"
    assert optimum.reason == REASON_MEDIO
    assert warm.warm_wet_hours == 3
    assert warm.opt_wet_hours == 0
    assert warm.score == 1
    assert warm.level == "bajo"
    assert warm.reason == REASON_BAJO_POCAS

    alto = assess_forecast(
        _forecast([{"date": "2026-10-10", "hours": _wet("2026-10-10", 6, 22), "tmax": 22}])
    ).days[0]
    assert alto.score == 4
    assert alto.level == "alto"
    assert alto.reason == REASON_ALTO


def test_cold_wet_day_is_bajo_even_with_rain_and_warm_tmax():
    cold = assess_forecast(
        _forecast(
            [
                {
                    "date": "2026-10-10",
                    "hours": _wet("2026-10-10", 8, 14.9),
                    "tmax": 25,
                    "precip_sum": 5,
                    "prob": 80,
                }
            ]
        )
    ).days[0]
    assert cold.wet_hours == 8
    assert cold.warm_wet_hours == 0
    assert cold.level == "bajo"
    assert cold.reason == REASON_BAJO_TEMP


def test_dry_day_and_rain_without_wet_hours():
    dry = assess_forecast(_forecast([{"date": "2026-10-10", "hours": [], "tmax": 30}])).days[0]
    assert dry.level == "bajo"
    assert dry.reason == REASON_BAJO_SECO

    rain = assess_forecast(
        _forecast([{"date": "2026-10-10", "hours": [], "tmax": 30, "precip_sum": 4}])
    ).days[0]
    assert rain.wet_hours == 0
    assert rain.level == "bajo"
    assert rain.reason == REASON_BAJO_LLUVIA


def test_consecutive_bonus_requires_previous_calendar_day():
    first = assess_forecast(
        _forecast(
            [
                {"date": "2026-10-10", "hours": _wet("2026-10-10", 6, 18), "tmax": 20},
                {"date": "2026-10-11", "hours": _wet("2026-10-11", 6, 18), "tmax": 20},
            ]
        )
    )
    assert first.days[0].consecutive_bonus is False
    assert first.days[1].consecutive_bonus is True
    assert first.days[1].score == first.days[0].score + 1


def test_missing_hours_and_wrong_timezone():
    short = {
        "timezone": "America/El_Salvador",
        "hourly": {
            "time": ["2026-10-10T00:00"],
            "temperature_2m": [22],
            "relative_humidity_2m": [95],
            "precipitation": [0],
        },
        "daily": {
            "time": ["2026-10-10"],
            "temperature_2m_max": [24],
            "precipitation_sum": [1],
            "precipitation_probability_max": [10],
        },
    }
    day = assess_forecast(short).days[0]
    assert day.level is None
    assert day.reason == REASON_SIN_DATOS

    wrong = assess_forecast({"timezone": "UTC", "hourly": short["hourly"], "daily": short["daily"]})
    assert wrong.available is False
    assert wrong.days == []


def test_temperature_edges_and_spray_window():
    def one(temperature, tmax):
        return assess_forecast(
            _forecast([{"date": "2026-10-10", "hours": _wet("2026-10-10", 1, temperature), "tmax": tmax}])
        ).days[0]

    assert one(15, 15).warm_wet_hours == 1
    assert one(30, 30).warm_wet_hours == 1
    assert one(21, 21).opt_wet_hours == 1
    assert one(25, 21).opt_wet_hours == 1
    assert one(20.9, 20).opt_wet_hours == 0
    assert one(25.1, 20).warm_wet_hours == 1

    hours = []
    for hour in range(6):
        hours.append(
            {
                "time": f"2026-10-10T{hour:02d}:00",
                "temperature_2m": 24,
                "relative_humidity_2m": 70,
                "precipitation": 0,
                "precipitation_probability": 10,
            }
        )
    window = next_dry_spray_window(_forecast([{"date": "2026-10-10", "hours": hours}])["hourly"])
    assert window is not None
    assert window.start.startswith("2026-10-10T00")


def test_synthetic_week_is_alto():
    week = assess_forecast(synthetic_forecast())
    assert week.available
    assert week.days[0].level == "alto"
    assert len(week.days) == 7
