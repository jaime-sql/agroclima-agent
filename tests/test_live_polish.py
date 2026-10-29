from agroclima_agent.english import to_english
from agroclima_agent.handoff import CENTA_LINE
from agroclima_agent.pipeline import NO_ALERT_MODEL, StepResult, _publish_plan, _step_used_fallback


class _Decision:
    def __init__(self, window="viernes 30, 7:00–10:00 a. m.", handoff=True):
        self.spray_window = window
        self.handoff_required = handoff


def test_no_alert_skip_is_not_a_fallback():
    step = StepResult(id="alertas", title="t", mock=False, farmer_text="x", citations=[],
                      model_id=NO_ALERT_MODEL, latency_ms=None, tokens=None, input_sha256="", detail={})
    assert _step_used_fallback(step) is False


def test_plan_punctuation_and_single_time_es():
    text = "Usted tiene riesgo alto. Realice la aplicación el viernes 30 entre las 6:00 y 9:00 a. m"
    out = _publish_plan(text, _Decision(), "es")
    assert ".." not in out
    assert "alto. Cuándo: viernes 30, 7:00–10:00 a. m. CENTA:" in out
    assert out.count(":00") == 2
    assert out.endswith(CENTA_LINE)


def test_plan_english_has_no_spanish():
    text = ("The decided level is alto. Dose note: dosis según etiqueta / su agrónomo. "
            "Classes: cobre, triazol, triazol+estrobilurina. Spray Friday 30 between 7:00–10:00 a.m.")
    out = _publish_plan(text, _Decision("Friday 30, 7:00–10:00 a.m."), "en")
    for word in ("alto", "dosis", "cobre", "triazol,", "estrobilurina", "a.m.."):
        assert word not in out
    assert "high" in out and "copper" in out and "triazole+strobilurin" in out
    assert "When: Friday 30, 7:00–10:00 a.m. CENTA:" in out
    assert out.count("7:00") == 1


def test_to_english_levels():
    assert to_english("riesgo medio") == "riesgo medium"


def test_plan_has_one_centa_link():
    text = "The risk is high. Tell your agronomist about the high-risk day; see https://www.centa.gob.sv for more info."
    out = _publish_plan(text, _Decision("Friday 30, 7:00–10:00 a.m."), "en")
    assert out.count("centa.gob.sv") == 1
    assert out.endswith(CENTA_LINE)
