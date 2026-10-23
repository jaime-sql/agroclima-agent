"""Technician handoff and the action plan. Rules only: no model call."""

from __future__ import annotations

from dataclasses import dataclass

from agroclima_agent.diagnosis import InterpretedDiagnosis
from agroclima_agent.risk import (
    DOSE_NOTE,
    FUNGICIDE_CLASSES,
    RISK_FOOTER,
    DayAssessment,
    SprayWindow,
    WeekAssessment,
    display_reason,
    worst_level,
)

CENTA_LINE = "CENTA: (503) 2397-2200, https://www.centa.gob.sv"


@dataclass(frozen=True)
class Decision:
    """Final plan. Narrative models may word this; they may not change it."""

    department: str
    worst: str | None
    reason: str
    plan_allowed: bool
    handoff_required: bool
    handoff_text: str
    fungicide_classes: tuple[str, ...]
    dose_note: str
    spray_window: str | None
    footer: str
    diagnosis_band: str | None
    diagnosis_label: str | None

    def template_es(self) -> str:
        level = self.worst or "sin datos"
        if not self.plan_allowed:
            action = "Qué: observe la finca y no aplique un producto solo con esta pantalla."
        elif level == "bajo":
            action = "Qué: siga revisando hojas. El clima de este departamento se ve menos favorable a la roya."
        else:
            classes = ", ".join(self.fungicide_classes)
            action = (
                f"Qué: si su agrónomo lo indica, use un producto de una de estas clases: {classes}. "
                "Cubra el envés de la hoja y alterne el modo de acción."
            )
        dose = f"Cuánto: {self.dose_note}."
        when = (
            f"Cuándo: próxima ventana seca {self.spray_window}."
            if self.spray_window
            else "Cuándo: no hay una ventana seca clara en este pronóstico."
        )
        parts = [
            f"Departamento: {self.department}. Peor nivel de la semana: {level}.",
            self.reason,
            action,
            dose,
            when,
        ]
        if self.handoff_text:
            parts.append(self.handoff_text)
        parts.append(self.footer)
        return " ".join(parts)

    def as_dict(self) -> dict:
        return {
            "department": self.department,
            "worst": self.worst,
            "reason": self.reason,
            "plan_allowed": self.plan_allowed,
            "handoff_required": self.handoff_required,
            "handoff_text": self.handoff_text,
            "fungicide_classes": list(self.fungicide_classes),
            "dose_note": self.dose_note,
            "spray_window": self.spray_window,
            "footer": self.footer,
            "diagnosis_band": self.diagnosis_band,
            "diagnosis_label": self.diagnosis_label,
        }


def _worst_day(days: list[DayAssessment]) -> DayAssessment | None:
    scored = [day for day in days if day.level]
    if not scored:
        return None
    return max(scored, key=lambda day: (LEVEL_RANK[day.level or "bajo"], day.date))


LEVEL_RANK = {"bajo": 1, "medio": 2, "alto": 3}


def _window_text(window: SprayWindow | None) -> str | None:
    if window is None:
        return None
    return f"{window.start} a {window.end}"


def decide(
    *,
    department: str,
    week: WeekAssessment,
    diagnosis: InterpretedDiagnosis | None,
    photo_supplied: bool,
    vision_mock: bool,
    spray_window: SprayWindow | None,
) -> Decision:
    worst = worst_level([day.level for day in week.days]) if week.available else None
    top = _worst_day(week.days) if week.available else None
    if top and top.level:
        reason = display_reason(top.reason)
    elif not week.available:
        reason = "No pudimos obtener el pronóstico. Revise su señal e intente de nuevo."
    else:
        reason = "No hay pronóstico completo para este departamento."

    plan_allowed = True
    handoff_required = False
    band = None
    label = None
    notes: list[str] = []

    if diagnosis is not None:
        band = diagnosis.band
        label = diagnosis.read.label
        plan_allowed = diagnosis.plan_allowed
        handoff_required = diagnosis.handoff_required
        if diagnosis.handoff_required:
            notes.append("Comparta este resultado con su agrónomo o cooperativa.")
    elif photo_supplied and vision_mock:
        plan_allowed = False
        handoff_required = True
        notes.append(
            "No llamamos al modelo de visión. No damos un plan a partir de la foto. "
            "Repita cuando el servicio esté activo, o consulte a su agrónomo."
        )
    elif photo_supplied:
        plan_allowed = False
        handoff_required = True
        notes.append("No pudimos leer la foto. Tome otra o consulte a su agrónomo.")

    if worst == "alto":
        handoff_required = True
        notes.append("Hay al menos un día alto. Avise a su agrónomo o cooperativa.")

    if handoff_required:
        notes.append(CENTA_LINE)

    # A retake asks for another photo and does not page a technician by itself,
    # unless the weather is already alto (handled above).
    if diagnosis is not None and diagnosis.read.label == "retomar" and worst != "alto":
        handoff_required = False
        notes = [note for note in notes if note != CENTA_LINE]

    return Decision(
        department=department,
        worst=worst,
        reason=reason,
        plan_allowed=plan_allowed and week.available,
        handoff_required=handoff_required,
        handoff_text=" ".join(dict.fromkeys(notes)),
        fungicide_classes=FUNGICIDE_CLASSES if plan_allowed and week.available else (),
        dose_note=DOSE_NOTE,
        spray_window=_window_text(spray_window) if plan_allowed else None,
        footer=RISK_FOOTER,
        diagnosis_band=band,
        diagnosis_label=label,
    )
