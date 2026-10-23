"""Refresh official rust alerts once per department per 24 hours.

This command is not the nightly risk job. Page loads do not call it.
"""

from __future__ import annotations

from agroclima_agent.alerts import AlertSearch
from agroclima_agent.audit import AuditLog
from agroclima_agent.config import load_settings
from agroclima_agent.places import departments


def main() -> None:
    settings = load_settings()
    search = AlertSearch(settings, AuditLog(settings.audit_log))
    for name in departments():
        rows = search.refresh(name)
        state = "sin actualizar" if any(row.stale for row in rows) else "actualizado"
        print(f"{name}: {state} ({len(rows)})")
