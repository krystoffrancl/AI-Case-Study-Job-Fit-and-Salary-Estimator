"""HTTP API: POST /evaluate (kick off async job) + GET /status/{job_id} (poll)."""
from __future__ import annotations

import asyncio
from collections import Counter

# držíme tasky aby je GC nesmetl před doběhnutím (asyncio.create_task vrací weak ref)
_BACKGROUND_TASKS: set[asyncio.Task] = set()

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from cv_evaluator.config import settings
from cv_evaluator.job_store import create_job, get_job, update_job
from cv_evaluator.log_store import current_job_id, log_store
from cv_evaluator.models import JobStatus, Report
from cv_evaluator.services.cost_tracker import cost_tracker
from cv_evaluator.services.embeddings import find_matching_positions
from cv_evaluator.steps.extractor import extract_cv_data
from cv_evaluator.steps.finalizer import finalize_report
from cv_evaluator.steps.growth_target import compute_growth_target
from cv_evaluator.steps.parser import parse_cv
from cv_evaluator.steps.quality_assessor import assess_quality
from cv_evaluator.steps.salary_anchor import compute_anchor
from cv_evaluator.steps.scorer import calculate_score
from cv_evaluator.utils.logger import logger

router = APIRouter()

ALLOWED_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


async def process_cv(job_id: str, file_bytes: bytes, filename: str) -> None:
    """Plný pipeline: parse → extract → score → retrieve → anchor → growth → finalize.

    Nastavuje `current_job_id` ContextVar – díky tomu všechny `logger.info(...)` volané
    v této async tasce (i v pod-funkcích) automaticky skončí v per-job log bufferu pro
    streaming na frontend.
    """
    current_job_id.set(job_id)
    try:
        logger.info(f"=== Pipeline start (job={job_id}, soubor={filename}, "
                    f"velikost={len(file_bytes)} B) ===")

        update_job(job_id, JobStatus.PARSING)
        cv_data = parse_cv(file_bytes, filename)

        update_job(job_id, JobStatus.EXTRACTING)
        extracted = await extract_cv_data(cv_data, job_id=job_id)
        tiers = Counter(s.tier for s in extracted.skills)
        logger.info(
            f"Extrakce hotová: {len(extracted.skills)} skills "
            f"(expert={tiers['expert']}, core={tiers['core']}, basic={tiers['basic']}, "
            f"unknown={tiers['unknown']}), {extracted.years_of_experience} let praxe, "
            f"trajectory={extracted.career_trajectory.direction}"
        )

        update_job(job_id, JobStatus.SCORING)
        score = calculate_score(extracted)
        logger.info(
            f"Skóre: {score.total}/100 "
            f"(exp={score.experience_score}, skills={score.skills_score}, "
            f"edu={score.education_score}, role={score.role_seniority_score}, "
            f"pers={score.personality_score})"
        )

        update_job(job_id, JobStatus.ESTIMATING)
        matches = find_matching_positions(extracted, k=settings.embedding_topk)
        logger.info(
            "Top matche: "
            + ", ".join(f"{m['position']} ({m['similarity']})" for m in matches)
        )

        anchor = compute_anchor(score, matches, trajectory=extracted.career_trajectory)
        growth_target = compute_growth_target(anchor, extracted)
        if growth_target is None:
            logger.info("Growth target: žádná dosažitelná role pro +30 %")
        else:
            logger.info(
                f"Growth target: {growth_target.target_role} "
                f"@ {growth_target.target_salary_czk} CZK "
                f"(similarity={growth_target.similarity})"
            )

        update_job(job_id, JobStatus.EXPLAINING)
        final = await finalize_report(
            extracted=extracted,
            score=score,
            matches=matches,
            anchor=anchor,
            growth_target=growth_target,
            job_id=job_id,
        )

        quality = assess_quality(extracted, matches)
        cost = cost_tracker.summary(job_id)
        logger.info(
            f"Quality: {quality.confidence} ({quality.score}); "
            f"cena: {cost.total_czk:.3f} Kč ({cost.calls} LLM volání)"
        )

        update_job(
            job_id,
            JobStatus.DONE,
            result=Report(
                extracted=extracted,
                seniority=score,
                salary=final.salary,
                salary_anchor=anchor,
                explanation=final.explanation,
                growth_plan=final.growth_plan,
                matches=matches,
                data_quality=quality,
                cost=cost,
            ),
        )
        logger.info("=== Pipeline dokončena ===")

    except Exception as e:
        logger.exception(f"Pipeline selhala: {e}")
        update_job(job_id, JobStatus.FAILED, error=str(e))


@router.post("/evaluate")
async def evaluate_cv(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(400, detail="Soubor nemá název.")
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            415,
            detail=f"Nepodporovaný formát. Povoleno: PDF, DOCX. Dostali jsme: {file.content_type}",
        )

    contents = await file.read()
    max_bytes = settings.max_file_size_mb * 1024 * 1024
    if len(contents) > max_bytes:
        raise HTTPException(
            413, detail=f"Soubor je příliš velký. Maximum je {settings.max_file_size_mb} MB."
        )

    job = create_job()
    task = asyncio.create_task(process_cv(job.id, contents, file.filename))
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)
    return JSONResponse(
        status_code=202,
        content={"job_id": job.id, "status": job.status},
    )


@router.get("/status/{job_id}")
async def get_status(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, detail="Job nenalezen.")
    return job


@router.get("/logs/{job_id}")
async def get_logs(job_id: str, since: int = 0):
    """Vrátí log entries pro daný job od indexu `since` (incremental polling).

    Response: { entries: [{ts, level, logger, message}, ...], next: int }
    """
    entries = log_store.get(job_id, since_index=since)
    return {
        "entries": [e.to_dict() for e in entries],
        "next": since + len(entries),
    }
