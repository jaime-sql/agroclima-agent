"""Official coffee-rust alerts via Tavily. Snippets are untrusted data."""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

from agroclima_agent.audit import AuditLog, AuditRecord, sha256_text
from agroclima_agent.config import Settings
from agroclima_agent.safety import as_data_block, guard_untrusted

OFFICIAL_SUFFIXES = (
    "centa.gob.sv",
    "mag.gob.sv",
    "isc.gob.sv",
    "oirsa.org",
    "iica.int",
    "fao.org",
)
TAVILY_URL = "https://api.tavily.com/search"
QUERY = "alerta oficial roya del cafeto Hemileia vastatrix El Salvador CENTA MAG"


@dataclass(frozen=True)
class Citation:
    title: str
    url: str
    snippet: str
    official: bool
    mock: bool

    def data_block(self) -> str:
        return as_data_block(self.url, self.title, self.snippet)


def host_is_official(url: str) -> bool:
    host = url.split("//", 1)[-1].split("/", 1)[0].lower()
    if host.startswith("www."):
        host = host[4:]
    return any(host == suffix or host.endswith("." + suffix) for suffix in OFFICIAL_SUFFIXES)


class AlertSearch:
    def __init__(self, settings: Settings, audit: AuditLog, transport: httpx.BaseTransport | None = None) -> None:
        self.settings = settings
        self.audit = audit
        self._transport = transport

    def search(self, department: str) -> list[Citation]:
        started = time.perf_counter()
        if not self.settings.tavily_configured:
            citations = [_mock_citation()]
            mock = True
            model_id = "mock"
        else:
            citations = self._live(department)
            mock = False
            model_id = "tavily"
        payload = "\n".join(item.data_block() for item in citations)
        self.audit.write(
            AuditRecord(
                step="alertas",
                input_sha256=sha256_text(f"{department}\n{QUERY}\n{payload}"),
                model_id=model_id,
                latency_ms=(time.perf_counter() - started) * 1000,
                tokens=None,
                mock=mock,
            )
        )
        return citations

    def _live(self, department: str) -> list[Citation]:
        body = {
            "query": f"{QUERY} {department}",
            "search_depth": "basic",
            "topic": "general",
            "max_results": 5,
            "include_answer": False,
            "include_domains": list(OFFICIAL_SUFFIXES),
        }
        headers = {
            "Authorization": f"Bearer {self.settings.tavily_api_key}",
            "Content-Type": "application/json",
        }
        try:
            with httpx.Client(transport=self._transport, timeout=20) as client:
                response = client.post(TAVILY_URL, headers=headers, json=body)
        except httpx.HTTPError:
            return []
        if response.status_code != 200:
            return []
        try:
            payload = response.json()
        except ValueError:
            return []
        results = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(results, list):
            return []
        citations: list[Citation] = []
        for item in results:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or "")
            title = str(item.get("title") or url or "Fuente")
            content = str(item.get("content") or "")
            if not url.startswith("https://") and not url.startswith("http://"):
                continue
            citations.append(
                Citation(
                    title=guard_untrusted(title, 300),
                    url=url,
                    snippet=guard_untrusted(content),
                    official=host_is_official(url),
                    mock=False,
                )
            )
        return citations


def _mock_citation() -> Citation:
    return Citation(
        title="[mock] Sample citation — not a live official alert",
        url="https://www.centa.gob.sv/",
        snippet=(
            "Mock mode: Tavily was not called. This row shows where a citation will appear. "
            "It is not a current rust bulletin."
        ),
        official=False,
        mock=True,
    )
