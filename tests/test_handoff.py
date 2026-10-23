from agroclima_agent.diagnosis import LeafRead, interpret
from agroclima_agent.handoff import decide
from agroclima_agent.risk import assess_forecast, synthetic_forecast


def _week():
    return assess_forecast(synthetic_forecast())


def _read(label, confidence, reason=None, mock=False):
    return interpret(LeafRead(label, confidence, reason, "nvidia/test", mock))


def test_retake_wins_and_blocks_the_plan():
    diagnosis = _read("retomar", 0.99, "borrosa")
    decision = decide(
        department="Santa Ana",
        week=_week(),
        diagnosis=diagnosis,
        photo_supplied=True,
        vision_mock=False,
        spray_window=None,
    )
    assert diagnosis.headline == "Repetir foto"
    assert decision.plan_allowed is False
    assert "kg" not in decision.template_es()
    assert decision.fungicide_classes == ()


def test_probable_roya_requires_handoff_and_keeps_class_names_only():
    diagnosis = _read("roya", 0.7)
    decision = decide(
        department="Santa Ana",
        week=_week(),
        diagnosis=diagnosis,
        photo_supplied=True,
        vision_mock=False,
        spray_window=None,
    )
    assert diagnosis.band == "probable"
    assert diagnosis.plan_allowed is True
    assert decision.handoff_required is True
    assert "centa.gob.sv" in decision.handoff_text
    assert decision.dose_note.startswith("dosis según etiqueta")
    text = decision.template_es()
    assert "cobre" in text
    assert "2.8" not in text


def test_healthy_leaf_needs_085_and_low_confidence_has_no_plan():
    unsure = _read("sana", 0.84)
    assert unsure.band == "no_seguro"
    assert unsure.plan_allowed is False
    sure = _read("sana", 0.85)
    assert sure.band == "seguro"
    assert sure.plan_allowed is True


def test_alto_weather_without_a_photo_still_hands_off():
    decision = decide(
        department="Ahuachapán",
        week=_week(),
        diagnosis=None,
        photo_supplied=False,
        vision_mock=True,
        spray_window=None,
    )
    assert decision.worst == "alto"
    assert decision.handoff_required is True
    assert decision.plan_allowed is True


def test_mock_vision_photo_does_not_authorize_a_plan():
    decision = decide(
        department="Santa Ana",
        week=_week(),
        diagnosis=None,
        photo_supplied=True,
        vision_mock=True,
        spray_window=None,
    )
    assert decision.plan_allowed is False
    assert decision.handoff_required is True
