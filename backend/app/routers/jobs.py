from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.services.jobs import get_job, list_jobs, start_job

router = APIRouter(tags=["jobs"])


def _results_dir(request: Request) -> Path:
    return request.app.state.results_dir  # type: ignore[attr-defined]


@router.get("/jobs")
def jobs(request: Request, fileId: str | None = None) -> dict[str, Any]:
    results_dir = _results_dir(request)
    return {"jobs": [j.__dict__ for j in list_jobs(results_dir, file_id=fileId)]}


@router.get("/jobs/{job_id}")
def job(job_id: str, request: Request) -> dict[str, Any]:
    results_dir = _results_dir(request)
    j = get_job(results_dir, job_id)
    if not j:
        raise HTTPException(status_code=404, detail="Job not found")
    return j.__dict__


@router.post("/jobs/extract/{file_id}")
def start_extract_job(file_id: str, request: Request, refresh: bool = False) -> dict[str, Any]:
    results_dir = _results_dir(request)

    # Lazy import to avoid circular deps.
    from app.routers.extraction import extract as run_extract

    def _run() -> dict[str, Any]:
        return run_extract(file_id=file_id, request=request, refresh=refresh)

    j = start_job(results_dir=results_dir, file_id=file_id, run=_run)
    return {"ok": True, "job": j.__dict__}

