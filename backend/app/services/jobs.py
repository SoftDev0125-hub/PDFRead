from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

JobStatus = Literal["queued", "running", "succeeded", "failed"]


@dataclass
class JobRecord:
    id: str
    file_id: str
    status: JobStatus
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None
    result_path: str | None = None


_LOCK = threading.Lock()
_JOBS: dict[str, JobRecord] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _job_dir(results_dir: Path) -> Path:
    d = results_dir / "_jobs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _job_path(results_dir: Path, job_id: str) -> Path:
    return _job_dir(results_dir) / f"{job_id}.json"


def _save_job(results_dir: Path, job: JobRecord) -> None:
    _job_path(results_dir, job.id).write_text(
        json.dumps(job.__dict__, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _load_job(results_dir: Path, job_id: str) -> JobRecord | None:
    p = _job_path(results_dir, job_id)
    if not p.exists():
        return None
    data = json.loads(p.read_text(encoding="utf-8"))
    return JobRecord(**data)


def get_job(results_dir: Path, job_id: str) -> JobRecord | None:
    with _LOCK:
        j = _JOBS.get(job_id)
    if j is not None:
        return j
    return _load_job(results_dir, job_id)


def list_jobs(results_dir: Path, file_id: str | None = None) -> list[JobRecord]:
    jobs: list[JobRecord] = []
    for p in _job_dir(results_dir).glob("*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            j = JobRecord(**data)
        except Exception:
            continue
        if file_id and j.file_id != file_id:
            continue
        jobs.append(j)
    jobs.sort(key=lambda x: x.created_at, reverse=True)
    return jobs


def start_job(
    *,
    results_dir: Path,
    file_id: str,
    run: callable,
) -> JobRecord:
    job_id = uuid.uuid4().hex
    job = JobRecord(id=job_id, file_id=file_id, status="queued", created_at=_now())
    with _LOCK:
        _JOBS[job_id] = job
    _save_job(results_dir, job)

    def _runner() -> None:
        nonlocal job
        with _LOCK:
            job.status = "running"
            job.started_at = _now()
            _JOBS[job_id] = job
        _save_job(results_dir, job)

        try:
            payload: dict[str, Any] = run()
            _ = payload  # extracted route already writes result file
            job.status = "succeeded"
            job.finished_at = _now()
            job.result_path = str((results_dir / f"{file_id}.json").resolve())
        except Exception as e:
            job.status = "failed"
            job.finished_at = _now()
            job.error = f"{type(e).__name__}: {e}"
        finally:
            _save_job(results_dir, job)
            with _LOCK:
                _JOBS[job_id] = job

        # Keep record available briefly (dev ergonomics).
        time.sleep(1.0)

    t = threading.Thread(target=_runner, daemon=True)
    t.start()
    return job

