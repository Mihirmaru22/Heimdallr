"""Heimdallr V2: Investigation State Persistence & Crash-Recovery Store.

Persists full investigation states and append-only audit logs to filesystem:
- Enables clean crash survival and long-horizon session resumption
- Guarantees deterministic state reconstruction
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
import re
from typing import Any

from argus.investigation.state import AuditTrailEntry, InvestigationState

logger = logging.getLogger(__name__)

DEFAULT_STORAGE_DIR = Path("/data/shared/project/PlayGround/Argus/storage/investigations")


class InvestigationStore:
    """Manages persistent serialization and recovery for active investigations."""

    def __init__(self, storage_dir: Path | str | None = None) -> None:
        self.storage_dir = Path(storage_dir or DEFAULT_STORAGE_DIR)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _sanitize_id(self, investigation_id: str) -> str:
        safe_id = Path(investigation_id).name
        clean_id = re.sub(r"[^a-zA-Z0-9_\-]", "", safe_id)
        return clean_id or "inv_default"

    def _state_path(self, investigation_id: str) -> Path:
        safe_id = self._sanitize_id(investigation_id)
        return self.storage_dir / f"{safe_id}.json"

    def _audit_path(self, investigation_id: str) -> Path:
        safe_id = self._sanitize_id(investigation_id)
        return self.storage_dir / f"{safe_id}_audit.jsonl"

    def save_state(self, state: InvestigationState) -> Path:
        """Persist full investigation state to disk atomically."""
        path = self._state_path(state.investigation_id)
        tmp_path = path.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(state.to_json(indent=2))
        tmp_path.replace(path)

        # Append only newly recorded audit entries
        self.append_audit_log(state.investigation_id, state.audit_trail)
        return path

    def load_state(self, investigation_id: str) -> InvestigationState:
        """Load persisted investigation state from disk."""
        path = self._state_path(investigation_id)
        if not path.exists():
            raise FileNotFoundError(f"Investigation {investigation_id} not found at {path}")
        with open(path, "r", encoding="utf-8") as f:
            return InvestigationState.from_json(f.read())

    def append_audit_log(self, investigation_id: str, entries: list[AuditTrailEntry]) -> None:
        """Append only unseen audit entries to JSONL stream."""
        audit_file = self._audit_path(investigation_id)
        existing_ids = set()
        if audit_file.exists():
            with open(audit_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            data = json.loads(line)
                            if "entry_id" in data:
                                existing_ids.add(data["entry_id"])
                        except Exception:
                            pass
        new_entries = [e for e in entries if e.entry_id not in existing_ids]
        if new_entries:
            with open(audit_file, "a", encoding="utf-8") as f:
                for e in new_entries:
                    f.write(e.model_dump_json() + "\n")

    def list_investigations(self) -> list[str]:
        """List all persisted investigation IDs."""
        return [
            p.stem for p in self.storage_dir.glob("*.json") if not p.name.endswith("_audit.jsonl")
        ]
