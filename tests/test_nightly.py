import json

from agroclima_agent.jobs.nightly import build_map, main
from agroclima_agent.open_meteo import FixtureSource
from agroclima_agent.places import load_places
from agroclima_agent.risk import synthetic_forecast


def test_fixture_map_covers_each_coffee_department(tmp_path, monkeypatch):
    payload = build_map(FixtureSource(synthetic_forecast()), load_places())
    names = [row["department"] for row in payload["departments"]]
    assert names == [
        "Ahuachapán",
        "Chalatenango",
        "La Libertad",
        "Morazán",
        "Santa Ana",
        "Sonsonate",
        "Usulután",
    ]
    assert all(row["worst"] == "alto" for row in payload["departments"])
    assert payload["model"] is None
    blob = json.dumps(payload)
    assert "NEBIUS_API_KEY" not in blob

    destination = tmp_path / "risk-map.json"
    monkeypatch.setattr(
        "sys.argv",
        ["agroclima-nightly", "--fixture", "--output", str(destination)],
    )
    main()
    written = json.loads(destination.read_text(encoding="utf-8"))
    assert len(written["departments"]) == 7
