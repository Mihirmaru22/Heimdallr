"""Record what a live research run read, and replay it offline.

A live run's quality depends on what the web returned at that moment. The recorder sits
between the investigation engine and the live retriever and writes every retrieval call
(search queries and their results, page fetches, robots.txt refusals and errors) to
``calls.jsonl`` in a run folder. ``ReplayCorpus`` answers the same calls from that file, so
the exact run can be re-executed and debugged on a machine without web access, and the
effect of a code change can be measured on real pages instead of guessed.
"""

from __future__ import annotations

from dataclasses import asdict, fields
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
from typing import Any

from argus.investigation.benchmark.corpus import InvestigationDocument
from argus.investigation.live_web.models import LiveWebEvidenceRecord

CALLS_FILE = "calls.jsonl"
META_FILE = "meta.json"


def run_folder_name(objective: str, when: datetime | None = None) -> str:
    when = when or datetime.now(timezone.utc)
    slug = re.sub(r"[^a-z0-9]+", "_", objective.lower()).strip("_")[:40] or "run"
    return f"{when.strftime('%Y%m%d_%H%M%S')}_{slug}"


def _git_commit() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=5, cwd=Path(__file__).parent)
        return out.stdout.strip()
    except Exception:
        return ""


def _doc_to_dict(doc: InvestigationDocument | None) -> dict[str, Any] | None:
    return asdict(doc) if doc is not None else None


def _doc_from_dict(data: dict[str, Any] | None) -> InvestigationDocument | None:
    if not data:
        return None
    names = {f.name for f in fields(InvestigationDocument)}
    return InvestigationDocument(**{k: v for k, v in data.items() if k in names})


def _record_from_dict(data: dict[str, Any]) -> LiveWebEvidenceRecord:
    names = {f.name for f in fields(LiveWebEvidenceRecord)}
    return LiveWebEvidenceRecord(**{k: v for k, v in data.items() if k in names})


def _limits(inner: Any) -> Any:
    try:
        return asdict(inner.limits)
    except Exception:
        return None


class RecordingCorpus:
    """Wraps a retriever; every retrieval call and the evidence records it produced are logged."""

    def __init__(self, inner: Any, run_dir: Path | str, objective: str = "") -> None:
        self.inner = inner
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self._calls = (self.run_dir / CALLS_FILE).open("a", encoding="utf-8")
        meta = {
            "objective": objective,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "commit": _git_commit(),
            "retriever": type(inner).__name__,
            "limits": _limits(inner),
        }
        (self.run_dir / META_FILE).write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)

    def _new_records(self, before: int) -> list[dict[str, Any]]:
        records = getattr(self.inner, "evidence_records", None) or []
        return [asdict(r) for r in records[before:]]

    def _log(self, entry: dict[str, Any]) -> None:
        self._calls.write(json.dumps(entry, default=str) + "\n")
        self._calls.flush()

    def _count(self) -> int:
        return len(getattr(self.inner, "evidence_records", None) or [])

    def search(self, query: str, limit: int = 5) -> list[InvestigationDocument]:
        before = self._count()
        docs = self.inner.search(query, limit=limit)
        self._log({"op": "search", "query": query, "limit": limit, "docs": [_doc_to_dict(d) for d in docs], "records": self._new_records(before)})
        return docs

    def get_by_url(self, url: str) -> InvestigationDocument | None:
        before = self._count()
        doc = self.inner.get_by_url(url)
        self._log({"op": "get_by_url", "url": url, "doc": _doc_to_dict(doc), "records": self._new_records(before)})
        return doc

    def get_document(self, identifier: str) -> InvestigationDocument | None:
        before = self._count()
        doc = self.inner.get_document(identifier)
        self._log({"op": "get_document", "url": identifier, "doc": _doc_to_dict(doc), "records": self._new_records(before)})
        return doc

    def is_known_blocked(self, url: str) -> bool:
        blocked = bool(self.inner.is_known_blocked(url)) if hasattr(self.inner, "is_known_blocked") else False
        self._log({"op": "is_known_blocked", "url": url, "result": blocked})
        return blocked

    def save_result(self, result: dict[str, Any]) -> Path:
        """Store the run's findings next to its calls, so a replay can be compared with it."""
        path = self.run_dir / "result.json"
        path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        self._calls.flush()
        return path


class ReplayCorpus:
    """Answers retrieval calls from a recorded run folder; nothing goes to the network.

    Calls are matched by operation and argument (query or URL). A repeated call gets the
    next recorded answer for that key, then the last one again. A call the run never made
    returns nothing and is counted in ``misses``, so replays show where a code change made
    the engine ask for something the recording cannot answer.
    """

    is_live_web = True

    def __init__(self, run_dir: Path | str) -> None:
        self.run_dir = Path(run_dir)
        self.meta: dict[str, Any] = {}
        meta_path = self.run_dir / META_FILE
        if meta_path.exists():
            self.meta = json.loads(meta_path.read_text(encoding="utf-8"))
        self._answers: dict[tuple[str, str], list[dict[str, Any]]] = {}
        self._served: dict[tuple[str, str], int] = {}
        for line in (self.run_dir / CALLS_FILE).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            entry = json.loads(line)
            key = (entry["op"], entry.get("query") or entry.get("url") or "")
            self._answers.setdefault(key, []).append(entry)
        self.cached_documents: dict[str, InvestigationDocument] = {}
        self.evidence_records: list[LiveWebEvidenceRecord] = []
        self.misses: list[tuple[str, str]] = []

    @property
    def objective(self) -> str:
        return self.meta.get("objective", "")

    @property
    def documents(self) -> dict[str, InvestigationDocument]:
        return self.cached_documents

    def _next(self, op: str, arg: str) -> dict[str, Any] | None:
        key = (op, arg)
        answers = self._answers.get(key)
        if not answers:
            self.misses.append(key)
            return None
        i = self._served.get(key, 0)
        self._served[key] = i + 1
        entry = answers[min(i, len(answers) - 1)]
        if i < len(answers):
            self.evidence_records.extend(_record_from_dict(r) for r in entry.get("records", []))
        return entry

    def _keep(self, doc: InvestigationDocument | None) -> InvestigationDocument | None:
        if doc is not None:
            self.cached_documents[doc.doc_id] = doc
        return doc

    def search(self, query: str, limit: int = 5) -> list[InvestigationDocument]:
        entry = self._next("search", query)
        docs = [_doc_from_dict(d) for d in (entry or {}).get("docs", [])]
        return [self._keep(d) for d in docs if d is not None]

    def get_by_url(self, url: str) -> InvestigationDocument | None:
        entry = self._next("get_by_url", url)
        return self._keep(_doc_from_dict((entry or {}).get("doc")))

    def get_document(self, identifier: str) -> InvestigationDocument | None:
        if identifier in self.cached_documents:
            return self.cached_documents[identifier]
        op = "get_document" if ("get_document", identifier) in self._answers else "get_by_url"
        entry = self._next(op, identifier)
        return self._keep(_doc_from_dict((entry or {}).get("doc")))

    def get_by_id(self, doc_id: str) -> InvestigationDocument | None:
        return self.cached_documents.get(doc_id)

    def is_known_blocked(self, url: str) -> bool:
        entry = self._answers.get(("is_known_blocked", url))
        return bool(entry and entry[-1].get("result"))

    def get_discoverable_entities(self) -> set[str]:
        return set()

    def register_discoverable_entity(self, entity: str) -> None:
        return None

    def reset_task_budget(self) -> None:
        return None
