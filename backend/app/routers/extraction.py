from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.services.openai_extract import extract_with_openai_two_pass
from app.services.page_pipeline import extract_pages_best_effort
from app.services.schema_extract import ExtractedAuthorizationV2, extract_schema_from_pages
from app.services.sheets_writer import append_authorization_row


router = APIRouter(tags=["extraction"])


def _uploads_dir(request: Request) -> Path:
    return request.app.state.uploads_dir  # type: ignore[attr-defined]


def _results_dir(request: Request) -> Path:
    return request.app.state.results_dir  # type: ignore[attr-defined]


def _load_meta(uploads_dir: Path) -> dict[str, Any]:
    p = uploads_dir / "_meta.json"
    if not p.exists():
        return {"files": []}
    return json.loads(p.read_text(encoding="utf-8"))


def _flatten_v2(v2: ExtractedAuthorizationV2) -> dict[str, Any]:
    """
    Backwards-compatible `extracted` object (flat values) for the frontend,
    while still returning v2 evidence under `extractedV2`.
    """
    return {
        "student_name": v2.student_name.value,
        "student_id": v2.student_id.value,
        "district": v2.district.value,
        "service_type": v2.service_type.value,
        "authorized_minutes": v2.authorized_minutes.value,
        "start_date": v2.start_date.value,
        "end_date": v2.end_date.value,
        "authorization_number": v2.authorization_number.value,
        "case_manager_name": v2.case_manager_name.value,
        "subject_areas": v2.subject_areas.value,
        "notes": v2.notes.value,
        "warnings": v2.warnings,
    }


@router.post("/extract/{file_id}")
def extract(file_id: str, request: Request) -> dict[str, Any]:
    uploads_dir = _uploads_dir(request)
    results_dir = _results_dir(request)
    meta = _load_meta(uploads_dir)
    rec = next((f for f in meta["files"] if f["id"] == file_id), None)
    if not rec:
        raise HTTPException(status_code=404, detail="File not found")

    pdf_path = uploads_dir / rec["storedName"]
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="File missing on disk")

    page_texts = extract_pages_best_effort(str(pdf_path))
    pages_for_schema = [(p.page_index, p.text) for p in page_texts]
    used_llm = False
    if os.getenv("OPENAI_API_KEY"):
        try:
            extracted_v2 = extract_with_openai_two_pass(pages_for_schema)
            used_llm = True
        except Exception as e:
            # Fall back to heuristic extraction, but surface the reason.
            extracted_v2 = extract_schema_from_pages(pages_for_schema)
            extracted_v2.warnings.append(f"LLM extraction failed; fell back to heuristic: {type(e).__name__}")
    else:
        extracted_v2 = extract_schema_from_pages(pages_for_schema)
    extracted_flat = _flatten_v2(extracted_v2)

    sheet_write: dict[str, Any] | None = None
    if os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON") and os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID"):
        try:
            sheet_write = append_authorization_row(
                extracted_flat,
                meta={
                    "fileId": file_id,
                    "originalName": rec.get("originalName"),
                    "receivedAt": datetime.now(timezone.utc).date().isoformat(),
                },
            )
        except Exception as e:
            extracted_v2.warnings.append(f"Google Sheets write failed: {type(e).__name__}")
            sheet_write = {"ok": False, "error": f"{type(e).__name__}"}

    payload = {
        "fileId": file_id,
        "originalName": rec["originalName"],
        "extracted": extracted_flat,
        "extractedV2": extracted_v2.model_dump(),
        "pageRouting": [{"page": p.page_index, "route": p.route, "chars": len(p.text)} for p in page_texts],
        "llmUsed": used_llm,
        "sheetWrite": sheet_write,
        "extractedAt": datetime.now(timezone.utc).isoformat(),
    }

    (results_dir / f"{file_id}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload

