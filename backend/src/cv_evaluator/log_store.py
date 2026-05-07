"""Per-job log capture pro streaming na frontend.

Trik: `current_job_id` je `ContextVar`, který se nastaví v `process_cv` a propaguje se
automaticky napříč všemi `await`-y v rámci tasku (asyncio kopíruje contextvars per task).
Každé `logger.info(...)` během pipeline tedy umíme přiřadit ke správnému jobu bez
nutnosti všude předávat job_id.
"""
from __future__ import annotations

import contextvars
import logging
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime
from threading import Lock

current_job_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_job_id", default=None
)

MAX_ENTRIES_PER_JOB = 500


@dataclass
class LogEntry:
    ts: str  # ISO 8601
    level: str  # INFO / WARNING / ERROR / DEBUG
    logger: str
    message: str

    def to_dict(self) -> dict:
        return asdict(self)


class JobLogStore:
    def __init__(self) -> None:
        self._buffers: dict[str, deque[LogEntry]] = {}
        self._lock = Lock()

    def append(self, job_id: str, entry: LogEntry) -> None:
        with self._lock:
            buf = self._buffers.get(job_id)
            if buf is None:
                buf = deque(maxlen=MAX_ENTRIES_PER_JOB)
                self._buffers[job_id] = buf
            buf.append(entry)

    def get(self, job_id: str, since_index: int = 0) -> list[LogEntry]:
        with self._lock:
            buf = self._buffers.get(job_id)
            if buf is None:
                return []
            return list(buf)[since_index:]


log_store = JobLogStore()


class JobLogHandler(logging.Handler):
    """Routes log records do per-job bufferu podle ContextVar `current_job_id`.

    Pokud contextvar není nastaven (např. startup logy mimo pipeline), záznam se zahodí
    – tady řešíme jen per-job streaming, nahrazujeme jen frontendovou viditelnost.
    """

    def emit(self, record: logging.LogRecord) -> None:
        try:
            job_id = current_job_id.get()
            if job_id is None:
                return
            entry = LogEntry(
                ts=datetime.utcnow().isoformat(timespec="milliseconds") + "Z",
                level=record.levelname,
                logger=record.name,
                message=self.format(record),
            )
            log_store.append(job_id, entry)
        except Exception:  # logging handler nesmí padat
            self.handleError(record)
