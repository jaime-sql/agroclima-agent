from agroclima_agent.alerts import Citation
from agroclima_agent.pipeline import alert_card_text


def _cite():
    return Citation(
        title="mayo 2025 - Ministerio de Agricultura y Ganadería",
        url="https://www.mag.gob.sv/wp-content/uploads/2025/09/MLMAG-2025.pdf",
        snippet="Se esperan lluvias intensas. Riesgo alto.",
        official=True,
        mock=False,
    )


def test_alert_card_is_title_date_link_only():
    for lang, label in (("es", "Consultado"), ("en", "Retrieved")):
        text = alert_card_text([_cite()], "30/10/2026", lang)
        assert text == (
            f"mayo 2025 - Ministerio de Agricultura y Ganadería — {label}: 30/10/2026 — "
            "https://www.mag.gob.sv/wp-content/uploads/2025/09/MLMAG-2025.pdf"
        )
        assert "lluvias" not in text and "riesgo" not in text.lower() and "risk" not in text.lower()
