"""Local colour-histogram baseline for leaf photos.

Orange-yellow pixels stand in for rust pustules and green pixels for the
leaf. This is an eval baseline, not a diagnosis and not a plan.
"""

from __future__ import annotations

from io import BytesIO

from PIL import Image

from agroclima_agent.diagnosis import LeafRead


def read_histogram(image: bytes) -> LeafRead:
    try:
        with Image.open(BytesIO(image)) as opened:
            rgb = opened.convert("RGB")
    except Exception:
        return LeafRead("retomar", 0, "otra", "colour-histogram-baseline", False)
    if rgb.width < 32 or rgb.height < 32:
        return LeafRead("retomar", 0, "lejos", "colour-histogram-baseline", False)
    sample = rgb.resize((64, 64))
    hsv = sample.convert("HSV")
    orange = 0
    green = 0
    pixels = hsv.load()
    total = hsv.width * hsv.height
    for y in range(hsv.height):
        for x in range(hsv.width):
            hue, saturation, value = pixels[x, y]
            if saturation < 40 or value < 40:
                continue
            if 8 <= hue <= 45:
                orange += 1
            elif 50 <= hue <= 120:
                green += 1
    colored = orange + green
    if colored < total * 0.15:
        return LeafRead("retomar", 0.2, "no_hoja", "colour-histogram-baseline", False)
    ratio = orange / colored
    if ratio >= 0.12:
        confidence = min(0.95, 0.55 + ratio)
        return LeafRead("roya", round(confidence, 4), None, "colour-histogram-baseline", False)
    if green / total > 0.45 and ratio < 0.04:
        return LeafRead("sana", 0.9, None, "colour-histogram-baseline", False)
    return LeafRead("otro", 0.7, None, "colour-histogram-baseline", False)
