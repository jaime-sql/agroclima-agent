from agroclima_agent.diagnosis import HistogramDiagnoser, parse_model_payload
from agroclima_agent.evaluation import LabelledDiagnoser, evaluate, synthetic_cases


def test_histogram_matches_synthetic_leaves_and_disagrees_with_a_constant():
    cases = synthetic_cases()
    scripted = LabelledDiagnoser({case.name: case.label for case in cases})
    report = evaluate(
        cases,
        {"scripted-vision": scripted, "colour-histogram-baseline": HistogramDiagnoser()},
    )
    scores = {row["name"]: row for row in report["scores"]}
    assert scores["scripted-vision"]["accuracy"] == 1
    assert scores["colour-histogram-baseline"]["accuracy"] == 1
    assert report["pairwise_agreement"]["rate"] == 1

    constant = LabelledDiagnoser({case.name: "roya" for case in cases})
    mixed = evaluate(cases, {"constant-roya": constant, "colour-histogram-baseline": HistogramDiagnoser()})
    mixed_scores = {row["name"]: row for row in mixed["scores"]}
    assert mixed_scores["colour-histogram-baseline"]["accuracy"] == 1
    assert mixed_scores["constant-roya"]["accuracy"] < 1
    assert mixed["pairwise_agreement"]["rate"] < 1


def test_vision_payload_parser():
    parsed = parse_model_payload(
        '```json\n{"label":"roya","confidence":0.91,"retake_reason":null}\n```',
        "nvidia/Nemotron-3.5-Super-VL",
    )
    assert parsed.label == "roya"
    assert parsed.confidence == 0.91
    broken = parse_model_payload("not json", "nvidia/Nemotron-3.5-Super-VL")
    assert broken.label == "retomar"
