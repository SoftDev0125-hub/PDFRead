from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse


router = APIRouter(tags=["files"])


def _uploads_dir(request: Request) -> Path:
    return request.app.state.uploads_dir  # type: ignore[attr-defined]


def _results_dir(request: Request) -> Path:
    return request.app.state.results_dir  # type: ignore[attr-defined]


def _meta_path(uploads_dir: Path) -> Path:
    return uploads_dir / "_meta.json"


def _load_meta(uploads_dir: Path) -> dict[str, Any]:
    p = _meta_path(uploads_dir)
    if not p.exists():
        return {"files": []}
    return json.loads(p.read_text(encoding="utf-8"))


def _save_meta(uploads_dir: Path, meta: dict[str, Any]) -> None:
    _meta_path(uploads_dir).write_text(json.dumps(meta, indent=2), encoding="utf-8")


@router.get("/files")
def list_files(request: Request) -> dict[str, Any]:
    uploads_dir = _uploads_dir(request)
    meta = _load_meta(uploads_dir)
    return meta


@router.post("/files")
async def upload_file(request: Request, file: UploadFile = File(...)) -> dict[str, Any]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")

    uploads_dir = _uploads_dir(request)
    fid = uuid.uuid4().hex
    safe_name = Path(file.filename).name
    dst = uploads_dir / f"{fid}__{safe_name}"

    content = await file.read()
    dst.write_bytes(content)

    now = datetime.now(timezone.utc).isoformat()
    meta = _load_meta(uploads_dir)
    meta["files"].append(
        {
            "id": fid,
            "originalName": safe_name,
            "storedName": dst.name,
            "sizeBytes": len(content),
            "uploadedAt": now,
            "contentType": file.content_type,
        }
    )
    _save_meta(uploads_dir, meta)
    return {"ok": True, "file": meta["files"][-1]}


@router.get("/files/{file_id}/download")
def download_file(file_id: str, request: Request) -> FileResponse:
    uploads_dir = _uploads_dir(request)
    meta = _load_meta(uploads_dir)
    rec = next((f for f in meta["files"] if f["id"] == file_id), None)
    if not rec:
        raise HTTPException(status_code=404, detail="File not found")

    path = uploads_dir / rec["storedName"]
    if not path.exists():
        raise HTTPException(status_code=404, detail="File missing on disk")

    return FileResponse(path, filename=rec["originalName"], media_type=rec.get("contentType") or None)


@router.get("/results/{file_id}.json")
def download_result(file_id: str, request: Request) -> FileResponse:
    results_dir = _results_dir(request)
    path = results_dir / f"{file_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Result not found")
    return FileResponse(path, filename=f"{file_id}.json", media_type="application/json")


@router.delete("/files/{file_id}")
def delete_file(file_id: str, request: Request) -> dict[str, Any]:
    uploads_dir = _uploads_dir(request)
    results_dir = _results_dir(request)
    meta = _load_meta(uploads_dir)

    rec = next((f for f in meta["files"] if f["id"] == file_id), None)
    if not rec:
        raise HTTPException(status_code=404, detail="File not found")

    # Remove from meta first (so repeated deletes are predictable even if disk is missing).
    meta["files"] = [f for f in meta["files"] if f["id"] != file_id]
    _save_meta(uploads_dir, meta)

    deleted_upload = False
    upload_path = uploads_dir / rec["storedName"]
    if upload_path.exists():
        upload_path.unlink()
        deleted_upload = True

    deleted_result = False
    result_path = results_dir / f"{file_id}.json"
    if result_path.exists():
        result_path.unlink()
        deleted_result = True

    return {"ok": True, "deleted": {"upload": deleted_upload, "result": deleted_result}}

