"""Per-job cost tracking pro LLM volání.

Aproximace nákladů z token usage – jednoduchá náhrada za LangSmith/Langfuse pro demo.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from threading import Lock

from langchain_core.callbacks import BaseCallbackHandler

from cv_evaluator.config import settings
from cv_evaluator.models import CostSummary
from cv_evaluator.utils.logger import logger

# USD per 1k tokens (k 2026-05).
COST_PER_1K_TOKENS: dict[str, dict[str, float]] = {
    "gpt-4.1-nano": {"input": 0.0001, "output": 0.0004},
    "gpt-4.1-mini": {"input": 0.0004, "output": 0.0016},
    "gpt-4.1": {"input": 0.002, "output": 0.008},
    "text-embedding-3-small": {"input": 0.00002, "output": 0.0},
    "text-embedding-3-large": {"input": 0.00013, "output": 0.0},
}


@dataclass
class CostEvent:
    job_id: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    ts: datetime = field(default_factory=datetime.utcnow)


class CostTracker:
    def __init__(self) -> None:
        self._events_by_job: dict[str, list[CostEvent]] = defaultdict(list)
        self._lock = Lock()

    def record(self, job_id: str, model: str, input_tokens: int, output_tokens: int) -> None:
        rates = COST_PER_1K_TOKENS.get(model)
        if rates is None:
            logger.warning(f"Neznámý model {model} – cenu počítám jako 0")
            cost = 0.0
        else:
            cost = (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1000
        event = CostEvent(job_id, model, input_tokens, output_tokens, cost)
        with self._lock:
            self._events_by_job[job_id].append(event)

    def summary(self, job_id: str) -> CostSummary:
        with self._lock:
            events = list(self._events_by_job.get(job_id, []))
        total_usd = sum(e.cost_usd for e in events)
        by_model: dict[str, float] = {}
        for e in events:
            by_model[e.model] = round(by_model.get(e.model, 0.0) + e.cost_usd, 6)
        return CostSummary(
            total_usd=round(total_usd, 6),
            total_czk=round(total_usd * settings.usd_to_czk, 4),
            calls=len(events),
            by_model=by_model,
        )


cost_tracker = CostTracker()


class CostCallback(BaseCallbackHandler):
    """LangChain callback – po LLM volání zapíše token usage do cost_trackeru."""

    def __init__(self, job_id: str | None, model: str) -> None:
        super().__init__()
        self.job_id = job_id
        self.model = model

    def on_llm_end(self, response, **kwargs) -> None:  # type: ignore[no-untyped-def]
        if self.job_id is None:
            return
        try:
            usage = (response.llm_output or {}).get("token_usage", {})
            input_tokens = usage.get("prompt_tokens", 0)
            output_tokens = usage.get("completion_tokens", 0)
            if input_tokens or output_tokens:
                cost_tracker.record(self.job_id, self.model, input_tokens, output_tokens)
                rates = COST_PER_1K_TOKENS.get(self.model, {"input": 0, "output": 0})
                cost = (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1000
                logger.info(
                    f"LLM call ({self.model}): in={input_tokens}, out={output_tokens}, "
                    f"cost=${cost:.5f}"
                )
        except Exception as e:  # callback nesmí shodit pipeline
            logger.warning(f"CostCallback chyba: {e}")
