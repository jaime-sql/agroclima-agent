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
    credits: int | None = None

    def as_dict(self) -> dict:
        return {
            "ts": datetime.now(timezone.utc).isoformat(),
            "step": self.step,
            "input_sha256": self.input_sha256,
            "model_id": self.model_id,
            "latency_ms": round(self.latency_ms, 3),
            "tokens": self.tokens,
            "mock": self.mock,
            "credits": self.credits,
        }


def tavily_usage(path: Path) -> dict:
    """Count real Tavily searches recorded in the audit log, and sum their credits."""
    count = 0
    credits = 0
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("step") != "tavily-search":
                continue
            cost = row.get("credits")
            if not isinstance(cost, int):
                continue
            count += 1
            credits += cost
    return {"count": count, "credits": credits}


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
