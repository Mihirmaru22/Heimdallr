"""JSON logs with secrets redacted. Page content and credentials never go to the log."""

from __future__ import annotations

import json
import logging
import re
import sys
from contextvars import ContextVar

request_id: ContextVar[str | None] = ContextVar("request_id", default=None)

_SECRET_RE = re.compile(
    r"(?i)(password|passwd|secret|token|api[_-]?key|authorization|cookie|set-cookie|csrf)"
    r"(\"?\s*[:=]\s*\"?)([^\s\",;&]+)"
)
_BEARER_RE = re.compile(r"(?i)\b(bearer|basic)\s+[a-z0-9._~+/=-]+")
_OPENROUTER_RE = re.compile(r"sk-or-[a-z0-9-]{8,}", re.I)


def redact(text: str) -> str:
    text = _BEARER_RE.sub(r"\1 [REDACTED]", text)
    text = _SECRET_RE.sub(r"\1\2[REDACTED]", text)
    return _OPENROUTER_RE.sub("[REDACTED]", text)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": redact(record.getMessage()),
        }
        rid = request_id.get()
        if rid:
            payload["request_id"] = rid
        if record.exc_info:
            payload["exc"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, default=str)


def configure(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    # httpx logs full URLs at INFO, which may include query strings; keep it quiet.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
