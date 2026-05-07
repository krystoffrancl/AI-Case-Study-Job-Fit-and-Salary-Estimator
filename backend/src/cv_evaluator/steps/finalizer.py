"""LLM call #2: finalizér (gpt-4.1-mini, T=0.2).

Vyrobí salary range (uvnitř kotvy), vysvětlení a actionable growth plan.
LLM volnost je omezená kotvou – `_clamp_to_anchor` defenzivně oseká výstup
mimo ±drift, kdyby model constraint ignoroval.
"""
from __future__ import annotations

import json
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
from cv_evaluator.models import ExtractedCV, FinalAnalysis, SalaryAnchor, SalaryEstimate, SeniorityScore
from cv_evaluator.prompts.finalizer import HUMAN_PROMPT, SYSTEM_PROMPT
from cv_evaluator.services.cost_tracker import CostCallback
from cv_evaluator.steps.growth_target import GrowthTargetContext
from cv_evaluator.utils.logger import logger

_RETRY_EXC = (
    openai.APITimeoutError,
    openai.RateLimitError,
    openai.APIConnectionError,
    openai.InternalServerError,
)


def _build_chain(job_id: str | None):
    callbacks = [CostCallback(job_id, settings.finalizer_model)] if job_id else []
    model = ChatOpenAI(
        model=settings.finalizer_model,
        temperature=settings.finalizer_temperature,
        api_key=settings.openai_api_key,
        callbacks=callbacks,
    ).with_structured_output(FinalAnalysis)
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        ("human", HUMAN_PROMPT),
    ])
    return prompt | model


def _serialize_target(target: GrowthTargetContext | None) -> dict | None:
    if target is None:
        return None
    return {
        "target_salary_czk": target.target_salary_czk,
        "target_role": target.target_role,
        "target_group": target.target_group,
        "target_high_czk": target.target_high_czk,
        "target_after5_czk": target.target_after5_czk,
        "similarity_to_profile": target.similarity,
        "target_duties": target.target_duties,
        "user_skills_already_relevant": target.user_skills_already_relevant,
    }


def _clamp_to_anchor(salary: SalaryEstimate, anchor: SalaryAnchor) -> SalaryEstimate:
    new_min = max(salary.min_czk, anchor.min_czk)
    new_max = min(salary.max_czk, anchor.max_czk)
    if new_max < new_min:  # LLM výrazně utekl mimo kotvu
        new_min, new_max = anchor.min_czk, anchor.max_czk
    salary.min_czk, salary.max_czk = new_min, new_max
    return salary


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=10),
    retry=retry_if_exception_type(_RETRY_EXC),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
async def finalize_report(
    extracted: ExtractedCV,
    score: SeniorityScore,
    matches: list[dict],
    anchor: SalaryAnchor,
    growth_target: GrowthTargetContext | None,
    job_id: str | None = None,
) -> FinalAnalysis:
    logger.info(
        f"Finalizer: volání {settings.finalizer_model} (T={settings.finalizer_temperature}), "
        f"anchor={anchor.center_czk} CZK, growth_target="
        f"{growth_target.target_role if growth_target else 'None'}"
    )
    chain = _build_chain(job_id)
    dump = lambda obj: json.dumps(obj, ensure_ascii=False, indent=2)

    result = await chain.ainvoke({
        "profile_json": dump(extracted.model_dump()),
        "score_json": dump(score.model_dump()),
        "matches_json": dump(matches),
        "anchor_json": dump(anchor.model_dump()),
        "growth_target_json": dump(_serialize_target(growth_target)),
    })
    assert isinstance(result, FinalAnalysis)

    raw_min, raw_max = result.salary.min_czk, result.salary.max_czk
    result.salary = _clamp_to_anchor(result.salary, anchor)
    if (raw_min, raw_max) != (result.salary.min_czk, result.salary.max_czk):
        logger.warning(
            f"Finalizer: LLM výstup ({raw_min}-{raw_max}) byl mimo kotvu, "
            f"clampnuto na ({result.salary.min_czk}-{result.salary.max_czk})"
        )
    logger.info(
        f"Finalizer hotovo: salary {result.salary.min_czk}-{result.salary.max_czk} CZK; "
        f"strengths={len(result.explanation.strengths)}, "
        f"weaknesses={len(result.explanation.weaknesses)}, "
        f"growth_steps={len(result.growth_plan.steps)}"
    )
    return result
