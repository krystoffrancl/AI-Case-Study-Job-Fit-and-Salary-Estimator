"""Centrální logger.

Dva výstupy:
1. stdout (pro docker logs / dev) – plný formát s časem a úrovní.
2. JobLogHandler – per-job ring buffer pro streaming na frontend.
"""
from __future__ import annotations

import logging

from cv_evaluator.log_store import JobLogHandler

_STDOUT_FORMAT = "%(asctime)s | %(levelname)s | %(message)s"
_BUFFER_FORMAT = "%(message)s"  # frontend zobrazuje vlastní timestamp z LogEntry


def _setup() -> logging.Logger:
    log = logging.getLogger("cv_evaluator")
    log.setLevel(logging.INFO)

    # Předejít duplikaci při hot-reloadu (uvicorn --reload).
    if log.handlers:
        return log

    stdout_h = logging.StreamHandler()
    stdout_h.setFormatter(logging.Formatter(_STDOUT_FORMAT, datefmt="%H:%M:%S"))
    log.addHandler(stdout_h)

    buffer_h = JobLogHandler()
    buffer_h.setFormatter(logging.Formatter(_BUFFER_FORMAT))
    log.addHandler(buffer_h)

    log.propagate = False
    return log


logger = _setup()
