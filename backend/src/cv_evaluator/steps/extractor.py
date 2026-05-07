"""LLM call #1: extrakce strukturovaných dat z CV (gpt-4.1-nano, T=0).

Skills jsou už klasifikované do tierů (expert/core/basic/unknown) přímo v rámci
tohoto volání – proto pipeline nepotřebuje samostatný normalizační krok ani
hardcoded taxonomii.
"""
from __future__ import annotations

import logging

import openai
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from cv_evaluator.config import settings
from cv_evaluator.models import CVData, ExtractedCV
from cv_evaluator.prompts.extractor import HUMAN_PROMPT, SYSTEM_PROMPT
from cv_evaluator.services.cost_tracker import CostCallback
from cv_evaluator.utils.logger import logger

# Retry jen na transient OpenAI errory; logické chyby (BadRequest atd.) padnou hned.
_RETRY_EXC = (
    openai.APITimeoutError,
    openai.RateLimitError,
    openai.APIConnectionError,
    openai.InternalServerError,
)


def _build_chain(job_id: str | None):
    callbacks = [CostCallback(job_id, settings.extraction_model)] if job_id else []
    model = ChatOpenAI(
        model=settings.extraction_model,
        temperature=settings.extraction_temperature,
        api_key=settings.openai_api_key,
        callbacks=callbacks,
    ).with_structured_output(ExtractedCV)

    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        ("human", HUMAN_PROMPT),
    ])
    return prompt | model


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=10),
    retry=retry_if_exception_type(_RETRY_EXC),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
async def extract_cv_data(cv_data: CVData, job_id: str | None = None) -> ExtractedCV:
    logger.info(
        f"Extractor: volání {settings.extraction_model} (T={settings.extraction_temperature}) "
        f"nad {len(cv_data.raw_text)} znaky"
    )
    chain = _build_chain(job_id)
    result = await chain.ainvoke({"cv_text": cv_data.raw_text})
    assert isinstance(result, ExtractedCV)
    logger.info(
        f"Extractor: role={result.current_role!r}, "
        f"předchozích rolí={len(result.previous_roles)}, "
        f"yoe={result.years_of_experience}, edu={result.education_level.value}, "
        f"jazyky={len(result.languages)}, obory={len(result.industries)}"
    )
    return result
