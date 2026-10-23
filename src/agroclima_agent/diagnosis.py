"""Leaf diagnosis behind one interface: NVIDIA vision, or the colour histogram."""

from __future__ import annotations

import json
from dataclasses import dataclass

from agroclima_agent.nebius import VISION_INSTRUCTION, NebiusClient

LABELS = ("roya", "sana", "otro", "retomar")
RETAKE_REASONS = ("borrosa", "no_hoja", "lejos", "otra")

ORIENTATION = "Esto es una orientación, no un diagnóstico. Confirme con un agrónomo."
SANA_DETAIL = "No vemos señales de roya en esta hoja. Revise otras plantas cada semana."
OTRO_DETAIL = "No parece roya, pero la hoja tiene algo. Esta app solo revisa roya."
UNSURE_DETAIL = "No le damos un plan para no aconsejarle mal. Envíe el resultado a su agrónomo o cooperativa."
CONFIRM = "Confirme con un agrónomo."

RETAKE_COPY = {
    "borrosa": (
        "La foto está borrosa.",
        "Sostenga el teléfono quieto con las dos manos. Toque la hoja en la pantalla para enfocar.",
    ),
    "no_hoja": (
        "No vemos una hoja de café.",
        "Ponga una sola hoja de café en el centro, sobre su mano o un papel.",
    ),
    "lejos": (
        "La hoja está muy lejos.",
        "Acérquese a un palmo de la hoja. Que la hoja llene la pantalla.",
    ),
    "otra": (
        "No pudimos revisar esta foto.",
        "Tome la foto de día, con buena luz y sin sol directo. Una sola hoja, de cerca.",
    ),
}


@dataclass(frozen=True)
class LeafRead:
    label: str
    confidence: float
    retake_reason: str | None
    model_id: str
    mock: bool


@dataclass(frozen=True)
class InterpretedDiagnosis:
    read: LeafRead
    band: str
    headline: str
    detail: str
    plan_allowed: bool
    handoff_required: bool
    percent: int


class LeafDiagnoser:
    """Interface implemented by the vision model and the histogram baseline."""

    model_id: str
    mock: bool

    def diagnose(self, image: bytes, media_type: str) -> LeafRead:
        raise NotImplementedError


class NvidiaVisionDiagnoser(LeafDiagnoser):
    def __init__(self, client: NebiusClient, model_id: str) -> None:
        self.client = client
        self.model_id = model_id
        self.mock = not client.settings.nebius_configured

    def diagnose(self, image: bytes, media_type: str) -> LeafRead:
        if self.mock:
            return LeafRead(
                label="retomar",
                confidence=0,
                retake_reason="otra",
                model_id=self.model_id,
                mock=True,
            )
        completion = self.client.complete(
            step="diagnostico",
            model=self.model_id,
            user_text=VISION_INSTRUCTION,
            mock_text="",
            system="You only return the JSON object requested in the user message.",
            image=(image, media_type),
        )
        if completion.error or completion.mock:
            return LeafRead("retomar", 0, "otra", self.model_id, completion.mock)
        return parse_model_payload(completion.text, self.model_id)


class HistogramDiagnoser(LeafDiagnoser):
    """Colour-histogram baseline. It never authorizes a fungicide plan."""

    model_id = "colour-histogram-baseline"
    mock = False

    def diagnose(self, image: bytes, media_type: str) -> LeafRead:
        from agroclima_agent.histogram import read_histogram

        return read_histogram(image)


def parse_model_payload(raw: str, model_id: str) -> LeafRead:
    trimmed = raw.strip()
    if trimmed.startswith("```"):
        trimmed = trimmed.split("\n", 1)[-1]
        trimmed = trimmed.removesuffix("```").strip()
    try:
        parsed = json.loads(trimmed)
    except json.JSONDecodeError:
        return LeafRead("retomar", 0, "otra", model_id, False)
    if not isinstance(parsed, dict):
        return LeafRead("retomar", 0, "otra", model_id, False)
    label = parsed.get("label")
    if label not in LABELS:
        return LeafRead("retomar", 0, "otra", model_id, False)
    confidence = parsed.get("confidence")
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
        confidence = 0
    reason = parsed.get("retake_reason")
    if reason not in RETAKE_REASONS:
        reason = None
    bounded = min(1.0, max(0.0, float(confidence)))
    return LeafRead(str(label), bounded, reason if label == "retomar" else reason, model_id, False)


def interpret(read: LeafRead) -> InterpretedDiagnosis:
    """Confidence bands from the AgroClima flow. Retake wins. Sana needs 0.85."""
    percent = round(read.confidence * 100)
    if read.label == "retomar":
        reason = read.retake_reason if read.retake_reason in RETAKE_COPY else "otra"
        detail, advice = RETAKE_COPY[reason]
        return InterpretedDiagnosis(
            read=read,
            band="no_seguro",
            headline="Repetir foto",
            detail=f"{detail} {advice}",
            plan_allowed=False,
            handoff_required=False,
            percent=percent,
        )
    unsure = read.confidence < 0.85 if read.label == "sana" else read.confidence < 0.60
    if unsure:
        return InterpretedDiagnosis(
            read=read,
            band="no_seguro",
            headline=f"No seguro · {percent} %",
            detail=UNSURE_DETAIL,
            plan_allowed=False,
            handoff_required=True,
            percent=percent,
        )
    band = "seguro" if read.confidence >= 0.80 else "probable"
    word = "Seguro" if band == "seguro" else "Probable"
    handoff = band == "probable" or read.label == "otro"
    if read.label == "sana":
        return InterpretedDiagnosis(
            read=read,
            band=band,
            headline="Parece sana",
            detail=f"{word} · {percent} %. {SANA_DETAIL}",
            plan_allowed=True,
            handoff_required=False,
            percent=percent,
        )
    if read.label == "otro":
        return InterpretedDiagnosis(
            read=read,
            band=band,
            headline="No parece roya",
            detail=f"{word} · {percent} %. {OTRO_DETAIL}",
            plan_allowed=False,
            handoff_required=True,
            percent=percent,
        )
    probable = f" {CONFIRM}" if band == "probable" else ""
    return InterpretedDiagnosis(
        read=read,
        band=band,
        headline="Parece roya",
        detail=f"{word} · {percent} %.{probable} {ORIENTATION}",
        plan_allowed=True,
        handoff_required=handoff,
        percent=percent,
    )
