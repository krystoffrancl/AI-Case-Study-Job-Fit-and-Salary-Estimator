"""Centralizovaná konfigurace přes pydantic-settings.

Hodnoty: env > .env > defaults. .env hledáme v repo rootu, pak v backend/, pak v cwd.
"""
from __future__ import annotations

from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_env_file() -> Path:
    candidates = [
        Path(__file__).parent.parent.parent.parent / ".env",  # repo root
        Path(__file__).parent.parent.parent / ".env",         # backend/
        Path.cwd() / ".env",
    ]
    return next((c for c in candidates if c.exists()), candidates[0])


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_find_env_file(),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    openai_api_key: SecretStr

    extraction_model: str = "gpt-4.1-nano"
    finalizer_model: str = "gpt-4.1-mini"
    embedding_model: str = "text-embedding-3-small"
    judge_model: str = "gpt-4.1-mini"

    extraction_temperature: float = 0.0
    finalizer_temperature: float = 0.2

    max_file_size_mb: int = 10
    embedding_topk: int = 3
    growth_search_k: int = 25  # širší vector search pro hledání cílové role

    growth_multiplier: float = 1.30
    anchor_drift_pct: float = 0.10  # max odchylka finalizer LLM od kotvy

    usd_to_czk: float = 23.0


settings = Settings()  # type: ignore[call-arg]
