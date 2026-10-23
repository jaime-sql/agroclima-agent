"""Compare a vision diagnoser with the colour-histogram baseline.

The hook scores labels on a fixed synthetic set. It does not call Nebius
unless a caller passes a live diagnoser. The default CLI stays offline.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass

from PIL import Image
from io import BytesIO

from agroclima_agent.diagnosis import HistogramDiagnoser, LeafDiagnoser, LeafRead


@dataclass(frozen=True)
class EvalCase:
    name: str
    image: bytes
    label: str


@dataclass(frozen=True)
class Score:
    name: str
    accuracy: float
    correct: int
    total: int


def _png(color: tuple[int, int, int], size: int = 64, blot: tuple[int, int, int] | None = None) -> bytes:
    image = Image.new("RGB", (size, size), color)
    if blot is not None:
        for x in range(20, 44):
            for y in range(20, 44):
                image.putpixel((x, y), blot)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def synthetic_cases() -> list[EvalCase]:
    return [
        EvalCase("green-leaf", _png((30, 140, 40)), "sana"),
        EvalCase("orange-pustules", _png((30, 140, 40), blot=(220, 100, 20)), "roya"),
        EvalCase("grey-card", _png((128, 128, 128)), "retomar"),
        EvalCase("tiny", _png((30, 140, 40), size=8), "retomar"),
    ]


class LabelledDiagnoser(LeafDiagnoser):
    """Test double that returns the case label. Stand-in for a vision model."""

    model_id = "scripted-vision"
    mock = True

    def __init__(self, labels: dict[str, str]) -> None:
        self.labels = labels
        self._order: list[str] = []

    def diagnose(self, image: bytes, media_type: str) -> LeafRead:
        name = self._order.pop(0)
        label = self.labels[name]
        confidence = 0.2 if label == "retomar" else 0.91
        reason = "no_hoja" if label == "retomar" else None
        return LeafRead(label, confidence, reason, self.model_id, True)


def evaluate(cases: list[EvalCase], diagnosers: dict[str, LeafDiagnoser]) -> dict:
    per_case = []
    totals = {name: 0 for name in diagnosers}
    for case in cases:
        row = {"name": case.name, "expected": case.label, "labels": {}}
        for name, diagnoser in diagnosers.items():
            if isinstance(diagnoser, LabelledDiagnoser):
                diagnoser._order.append(case.name)
            read = diagnoser.diagnose(case.image, "image/png")
            row["labels"][name] = read.label
            if read.label == case.label:
                totals[name] += 1
        per_case.append(row)
    names = list(diagnosers)
    agreement = 0
    if len(names) >= 2:
        left, right = names[0], names[1]
        agreement = sum(1 for row in per_case if row["labels"][left] == row["labels"][right])
    count = len(cases)
    return {
        "cases": count,
        "scores": [
            {
                "name": name,
                "correct": totals[name],
                "total": count,
                "accuracy": round(totals[name] / count, 4) if count else 0,
            }
            for name in names
        ],
        "pairwise_agreement": {
            "left": names[0] if names else None,
            "right": names[1] if len(names) > 1 else None,
            "matches": agreement if len(names) >= 2 else None,
            "rate": round(agreement / count, 4) if count and len(names) >= 2 else None,
        },
        "rows": per_case,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare leaf diagnosers on synthetic photos")
    parser.add_argument("--json", action="store_true", help="Print the report as JSON")
    args = parser.parse_args()
    cases = synthetic_cases()
    scripted = LabelledDiagnoser({case.name: case.label for case in cases})
    report = evaluate(
        cases,
        {"scripted-vision": scripted, "colour-histogram-baseline": HistogramDiagnoser()},
    )
    if args.json:
        print(json.dumps(report, indent=2))
        return
    for score in report["scores"]:
        print(f"{score['name']}: {score['correct']}/{score['total']} ({score['accuracy']:.0%})")
    pair = report["pairwise_agreement"]
    print(f"agreement {pair['left']} vs {pair['right']}: {pair['matches']}/{report['cases']}")
