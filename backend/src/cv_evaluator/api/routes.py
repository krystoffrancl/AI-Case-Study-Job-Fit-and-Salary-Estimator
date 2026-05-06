import asyncio
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse

from cv_evaluator.job_store import create_job, get_job, update_job
from cv_evaluator.models import JobStatus, Report
from cv_evaluator.services.embeddings import find_matching_positions
from cv_evaluator.steps.extractor import extract_cv_data
from cv_evaluator.steps.finalizer import finalize_report
from cv_evaluator.steps.parser import parse_cv
from cv_evaluator.steps.scorer import calculate_score
from cv_evaluator.utils.logger import logger

router = APIRouter()

ALLOWED_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


async def process_cv(job_id: str, file_bytes: bytes, filename: str):
    try:
        logger.info(f"[{job_id}] Spouštím pipeline pro {filename}")

        update_job(job_id, JobStatus.PARSING)
        cv_data = parse_cv(file_bytes, filename)
        logger.info(f"[{job_id}] Parsování OK – {len(cv_data.raw_text)} znaků")

        update_job(job_id, JobStatus.EXTRACTING)
        extracted = await extract_cv_data(cv_data)
        logger.info(
            f"[{job_id}] Extrakce OK – {len(extracted.skills)} skills, "
            f"{extracted.years_of_experience} let praxe"
        )

        update_job(job_id, JobStatus.SCORING)
        score = calculate_score(extracted)
        logger.info(f"[{job_id}] Skóre seniority: {score.total}/100")

        update_job(job_id, JobStatus.ESTIMATING)
        matches = find_matching_positions(extracted, k=3)
        logger.info(
            f"[{job_id}] Matche: " + ", ".join(
                f"{m['position']} ({m['similarity']})" for m in matches
            )
        )

        update_job(job_id, JobStatus.EXPLAINING)
        final = await finalize_report(extracted, score, matches)

        report = Report(
            extracted=extracted,
            seniority=score,
            salary=final.salary,
            explanation=final.explanation,
            matches=matches,
        )
        update_job(job_id, JobStatus.DONE, result=report)
        logger.info(f"[{job_id}] Pipeline dokončena")

    except Exception as e:
        logger.exception(f"[{job_id}] Chyba: {e}")
        update_job(job_id, JobStatus.FAILED, error=str(e))


@router.post("/evaluate")
async def evaluate_cv(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Soubor nemá název.")

    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Nepodporovaný formát. Povoleno: PDF, DOCX. Dostali jsme: {file.content_type}",
        )

    contents = await file.read()

    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail="Soubor je příliš velký. Maximum je 10 MB.",
        )

    job = create_job()
    asyncio.create_task(process_cv(job.id, contents, file.filename))

    return JSONResponse(
        status_code=202,
        content={"job_id": job.id, "status": job.status},
    )


@router.get("/status/{job_id}")
async def get_status(job_id: str):
    job = get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job nenalezen.")

    return job
