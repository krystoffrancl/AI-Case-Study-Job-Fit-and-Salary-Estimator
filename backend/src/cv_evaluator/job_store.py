"""In-memory job store. Joby nepřežijí restart – pro produkci by se hodil Redis."""
from __future__ import annotations

import uuid
from typing import Any

from cv_evaluator.models import Job, JobStatus

_jobs: dict[str, Job] = {}


def create_job() -> Job:
    job = Job(id=str(uuid.uuid4()), status=JobStatus.RECEIVED)
    _jobs[job.id] = job
    return job


def get_job(job_id: str) -> Job | None:
    return _jobs.get(job_id)


def update_job(
    job_id: str,
    status: JobStatus,
    result: Any = None,
    error: str | None = None,
) -> None:
    """Pozor: result/error se přepisují na None při každém průchodu –
    nastav je jen v terminálních stavech (DONE, FAILED)."""
    if job_id in _jobs:
        _jobs[job_id].status = status
        _jobs[job_id].result = result
        _jobs[job_id].error = error
