"""Official coffee-rust alerts via Tavily. Snippets are untrusted data.

User requests never call Tavily. A separate refresh fetches each department
at most once every 24 hours with search_depth=basic (1 credit). The nightly
risk job does not use this module.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable
from zoneinfo import ZoneInfo

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
# Basic search only. Extract, crawl, and map are never requested.
TAVILY_URL = "https://api.tavily.com/search"
SEARCH_DEPTH = "basic"
BASIC_SEARCH_CREDITS = 1
MAX_RESULTS = 5
QUERY = "alerta oficial roya del cafeto Hemileia vastatrix El Salvador CENTA MAG"
CACHE_TTL = timedelta(hours=24)
SV = ZoneInfo("America/El_Salvador")
EMPTY_ALERT_TITLE = "Sin alerta oficial"


@dataclass(frozen=True)
class Citation:
    title: str
    url: str
    snippet: str
    official: bool
    mock: bool
    stale: bool = False

    def data_block(self) -> str:
        return as_data_block(self.url, self.title, self.snippet)


def host_is_official(url: str) -> bool:
    host = url.split("//", 1)[-1].split("/", 1)[0].lower()
    if host.startswith("www."):
        host = host[4:]
    return any(host == suffix or host.endswith("." + suffix) for suffix in OFFICIAL_SUFFIXES)


def query_for(department: str) -> str:
    return f"{QUERY} {department}"


def basic_search_body(department: str) -> dict:
    """The only Tavily request this app is allowed to send."""
    if SEARCH_DEPTH != "basic":
        raise RuntimeError("Tavily search_depth must stay basic")
    if MAX_RESULTS > 5:
        raise RuntimeError("Tavily max_results must stay at most 5")
    return {
        "query": query_for(department),
        "search_depth": "basic",
        "topic": "general",
        "max_results": MAX_RESULTS,
        "include_answer": False,
        "include_domains": list(OFFICIAL_SUFFIXES),
    }


class AlertSearch:
    def __init__(
        self,
        settings: Settings,
        audit: AuditLog,
        transport: httpx.BaseTransport | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.settings = settings
        self.audit = audit
        self._transport = transport
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def search(self, department: str) -> list[Citation]:
        """Serve the shared cache. This method never calls Tavily."""
        started = time.perf_counter()
        if not self.settings.tavily_configured:
            citations = [_empty_notice(department)]
            mock = False
            model_id = "template/fallback"
        else:
            citations = self._cached(department)
            mock = False
            model_id = "tavily-cache"
        self._audit_read(department, citations, model_id, mock, started)
        return citations

    def refresh(self, department: str) -> list[Citation]:
        """Fetch this department if the shared cache is older than 24 hours.

        A page load must not call this. The nightly risk job must not call this.
        """
        if not self.settings.tavily_configured:
            return [_empty_notice(department)]
        entry = self._entry(department)
        if entry is not None and self._is_fresh(entry):
            return _citations_from(entry, stale=False)
        if not self._budget_allows():
            return self._mark_stale(department, entry)
        self._spend()
        started = time.perf_counter()
        citations, error = self._basic_search(department)
        self.audit.write(
            AuditRecord(
                step="tavily-search",
                input_sha256=sha256_text(query_for(department)),
                model_id="tavily",
                latency_ms=(time.perf_counter() - started) * 1000,
                tokens=None,
                mock=False,
                credits=BASIC_SEARCH_CREDITS,
            )
        )
        if error or not citations:
            return self._mark_stale(department, entry)
        self._store(department, citations)
        return citations

    def _cached(self, department: str) -> list[Citation]:
        entry = self._entry(department)
        if entry is None:
            return [_empty_notice(department)]
        return _citations_from(entry, stale=not self._is_fresh(entry))

    def _mark_stale(self, department: str, entry: dict | None) -> list[Citation]:
        if entry is None:
            return [_empty_notice(department)]
        return _citations_from(entry, stale=True)

    def _basic_search(self, department: str) -> tuple[list[Citation], str | None]:
        body = basic_search_body(department)
        if body["search_depth"] != "basic" or body["max_results"] > 5:
            return [], "refused"
        headers = {
            "Authorization": f"Bearer {self.settings.tavily_api_key}",
            "Content-Type": "application/json",
        }
        try:
            with httpx.Client(transport=self._transport, timeout=20) as client:
                response = client.post(TAVILY_URL, headers=headers, json=body)
        except httpx.HTTPError:
            return [], "transport"
        if response.status_code != 200:
            return [], f"http_{response.status_code}"
        try:
            payload = response.json()
        except ValueError:
            return [], "bad_json"
        results = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(results, list):
            return [], "bad_json"
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
                    stale=False,
                )
            )
        return citations, None

    def _entry(self, department: str) -> dict | None:
        cache = _read_json(self.settings.tavily_cache_path)
        entry = cache.get(department)
        return entry if isinstance(entry, dict) else None

    def _is_fresh(self, entry: dict) -> bool:
        raw = entry.get("fetched_at")
        if not isinstance(raw, str):
            return False
        try:
            fetched = datetime.fromisoformat(raw)
        except ValueError:
            return False
        if fetched.tzinfo is None:
            fetched = fetched.replace(tzinfo=timezone.utc)
        return self._clock() - fetched < CACHE_TTL

    def _store(self, department: str, citations: list[Citation]) -> None:
        cache = _read_json(self.settings.tavily_cache_path)
        cache[department] = {
            "query": query_for(department),
            "fetched_at": self._clock().isoformat(),
            "citations": [asdict(item) for item in citations],
        }
        _write_json(self.settings.tavily_cache_path, cache)

    def _counter(self) -> dict:
        raw = _read_json(self.settings.tavily_counter_path)
        today = self._clock().astimezone(SV).date().isoformat()
        try:
            total = int(raw.get("total") or 0)
        except (TypeError, ValueError):
            total = 0
        try:
            daily = int(raw.get("daily") or 0)
        except (TypeError, ValueError):
            daily = 0
        if raw.get("day") != today:
            daily = 0
        return {"day": today, "daily": max(0, daily), "total": max(0, total)}

    def _budget_allows(self) -> bool:
        counter = self._counter()
        return (
            counter["daily"] < self.settings.tavily_daily_cap
            and counter["total"] < self.settings.tavily_total_cap
        )

    def _spend(self) -> None:
        counter = self._counter()
        counter["daily"] += 1
        counter["total"] += 1
        _write_json(self.settings.tavily_counter_path, counter)

    def _audit_read(
        self,
        department: str,
        citations: list[Citation],
        model_id: str,
        mock: bool,
        started: float,
    ) -> None:
        payload = "\n".join(item.data_block() for item in citations)
        self.audit.write(
            AuditRecord(
                step="alertas",
                input_sha256=sha256_text(f"{department}\n{QUERY}\n{payload}"),
                model_id=model_id,
                latency_ms=(time.perf_counter() - started) * 1000,
                tokens=None,
                mock=mock,
                credits=0,
            )
        )


def empty_alert_line(department: str, language: str = "es") -> str:
    """One honest sentence when this department has no saved official alert."""
    if language == "en":
        return f"No official alert was found for {department}."
    return f"No encontramos una alerta oficial para {department}."


def is_placeholder_alert(citation: Citation) -> bool:
    return citation.title == EMPTY_ALERT_TITLE


def _empty_notice(department: str) -> Citation:
    line = empty_alert_line(department)
    return Citation(
        title=EMPTY_ALERT_TITLE,
        url="https://www.centa.gob.sv/",
        snippet=line,
        official=False,
        mock=False,
        stale=True,
    )


def _citations_from(entry: dict, *, stale: bool) -> list[Citation]:
    raw_items = entry.get("citations")
    if not isinstance(raw_items, list) or not raw_items:
        return [_empty_notice(str(entry.get("query") or ""))]
    citations: list[Citation] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        snippet = str(item.get("snippet") or "")
        if stale and not snippet.lower().startswith("sin actualizar"):
            snippet = f"sin actualizar. {snippet}"
        citations.append(
            Citation(
                title=str(item.get("title") or "Fuente"),
                url=str(item.get("url") or "https://www.centa.gob.sv/"),
                snippet=snippet,
                official=bool(item.get("official")) and not stale,
                mock=False,
                stale=stale,
            )
        )
    return citations or [_empty_notice("")]


def _read_json(path) -> dict:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
