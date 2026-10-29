"""English copy for decision values that are stored in Spanish."""

from __future__ import annotations

import re

PHRASES = (
    ("«Hojas mojadas muchas horas y clima tibio: la roya se pega fácil.»", "Leaves stay wet for many hours in warm weather: rust spreads easily."),
    ("Hojas mojadas muchas horas y clima tibio: la roya se pega fácil.", "Leaves stay wet for many hours in warm weather: rust spreads easily."),
    ("«Humedad o lluvia algunas horas: riesgo moderado.»", "Humidity or rain for some hours: moderate risk."),
    ("«Día seco: la roya casi no avanza.»", "Dry day: rust barely spreads."),
    ("«Temperatura poco favorable para la roya.»", "Temperature is not favorable for rust."),
    ("«Pocas horas húmedas favorables; riesgo bajo de roya»", "Few wet hours favor rust; low rust risk."),
    ("«Llueve, pero sin horas húmedas favorables a la roya»", "Rain, but no wet hours that favor rust."),
    ("«sin datos»", "no data"),
    ("«pronóstico no disponible»", "forecast not available"),
    ("Hay al menos un día alto. Avise a su agrónomo o cooperativa.", "There is at least one high-risk day. Tell your agronomist or cooperative."),
    ("No pudimos leer la foto. Tome otra o consulte a su agrónomo.", "We could not read the photo. Take another one or ask your agronomist."),
    (
        "Estos umbrales de riesgo son una estimación nuestra y no han sido validados por el ISC, CENTA ni el MAG.",
        "These risk thresholds are our own estimate and have not been validated by ISC, CENTA or MAG.",
    ),
    ("dosis según etiqueta / su agrónomo", "dose as on the product label or as your agronomist says"),
    ("triazol+estrobilurina", "triazole+strobilurin"),
)
WORDS = (
    (r"\bcobre\b", "copper"),
    (r"\btriazol\b", "triazole"),
    (r"\balto\b", "high"),
    (r"\bmedio\b", "medium"),
    (r"\bbajo\b", "low"),
    (r"\bsin datos\b", "no data"),
)
LEVELS = {"bajo": "low", "medio": "medium", "alto": "high"}


def to_english(text: str) -> str:
    out = text
    for es, en in PHRASES:
        out = out.replace(es, en)
    for pattern, en in WORDS:
        out = re.sub(pattern, en, out, flags=re.IGNORECASE)
    return out


def payload_to_english(payload: dict) -> dict:
    out = dict(payload)
    for key, value in payload.items():
        if isinstance(value, str):
            out[key] = to_english(value)
        elif isinstance(value, list):
            out[key] = [to_english(v) if isinstance(v, str) else v for v in value]
    return out
