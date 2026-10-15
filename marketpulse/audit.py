"""Append-only JSONL audit log: what was said, what was extracted, what changed, what ran."""

from __future__ import annotations

import datetime as dt
import json
import threading
from pathlib import Path
from typing import Any


class AuditLog:
    def __init__(self, path: str | Path | None = "logs/audit.jsonl"):
        self.path = Path(path) if path else None
        self._lock = threading.Lock()
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, request_id: str, endpoint: str, **fields: Any) -> dict[str, Any]:
        rec = {
            "ts": dt.datetime.now(dt.UTC).isoformat(timespec="milliseconds"),
            "request_id": request_id,
            "endpoint": endpoint,
            **fields,
        }
        if self.path:
            with self._lock, self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        return rec

    def read(self) -> list[dict[str, Any]]:
        if not self.path or not self.path.exists():
            return []
        return [json.loads(x) for x in self.path.read_text(encoding="utf-8").splitlines() if x]
