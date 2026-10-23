"""JSONL audit of each agent step. Inputs are hashed; secrets are not written."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


@dataclass
class AuditRecord:
    step: str
    input_sha256: str
    model_id: str
    latency_ms: float
    tokens: dict | None
    mock: bool

    def as_dict(self) -> dict:
        return {
            "ts": datetime.now(timezone.utc).isoformat(),
            "step": self.step,
            "input_sha256": self.input_sha256,
            "model_id": self.model_id,
            "latency_ms": round(self.latency_ms, 3),
            "tokens": self.tokens,
            "mock": self.mock,
        }


class AuditLog:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.records: list[dict] = []

    def write(self, record: AuditRecord) -> dict:
        payload = record.as_dict()
        self.records.append(payload)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        return payload
