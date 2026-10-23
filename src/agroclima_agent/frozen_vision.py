"""Load the sealed leaf-vision request. The prompt text is not rewritten here."""

from __future__ import annotations

import json
from pathlib import Path


def frozen_config_path() -> Path:
    return Path(__file__).resolve().parent / "data" / "frozen_config.json"


def load_frozen_vision() -> dict:
    """Read frozen_config.json at runtime."""
    payload = json.loads(frozen_config_path().read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("frozen_config.json must be a JSON object")
    return payload


def vision_call(frozen: dict) -> dict:
    """Fields the leaf call sends. Prompt bytes stay as stored in the file."""
    prompt = frozen.get("prompt")
    model = frozen.get("model")
    if frozen.get("prompt_version") != "v1" or not isinstance(prompt, str) or not prompt:
        raise ValueError("frozen vision prompt must be v1")
    if not isinstance(model, str) or not model:
        raise ValueError("frozen vision model is missing")
    reasoning = str(frozen.get("reasoning", "")).replace(" ", "")
    if "enable_thinking=false" not in reasoning:
        raise ValueError("frozen vision reasoning must be off")
    temperature = frozen.get("temperature")
    max_tokens = frozen.get("max_tokens")
    if isinstance(temperature, bool) or not isinstance(temperature, (int, float)):
        raise ValueError("frozen vision temperature is missing")
    if isinstance(max_tokens, bool) or not isinstance(max_tokens, int):
        raise ValueError("frozen vision max_tokens is missing")
    return {
        "model": model,
        "prompt": prompt,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "chat_template_kwargs": {"enable_thinking": False},
    }
