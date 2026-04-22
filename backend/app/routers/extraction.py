from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.services.lab_openai_extract import extract_with_openai_two_pass
from app.services.lab_schema import ExtractedLabReportV2, extract_lab_schema_heuristic
from app.services.page_pipeline import extract_pages_best_effort


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


def _flatten_v2(v2: ExtractedLabReportV2) -> dict[str, Any]:
    """
    Backwards-compatible `extracted` object (flat values) for the frontend,
    while still returning v2 evidence under `extractedV2`.
    """
    return {
        "patient_name": v2.patient_name.value,
        "age_years": v2.age_years.value,
        "sex": v2.sex.value,
        "report_date": v2.report_date.value,
        "source": v2.source.value,
        "biomarkers": [
            {
                "name": b.name.value,
                "original_name": b.original_name.value,
                "value": b.value.value,
                "unit": b.unit.value,
                "reference_range_text": b.reference_range_text.value,
                "status": b.status.value,
                "notes": b.notes.value,
            }
            for b in v2.biomarkers
        ],
        "warnings": v2.warnings,
    }


@router.post("/extract/{file_id}")
def extract(file_id: str, request: Request, refresh: bool = False) -> dict[str, Any]:
    uploads_dir = _uploads_dir(request)
    results_dir = _results_dir(request)
    meta = _load_meta(uploads_dir)
    rec = next((f for f in meta["files"] if f["id"] == file_id), None)
    if not rec:
        raise HTTPException(status_code=404, detail="File not found")

    result_path = results_dir / f"{file_id}.json"
    if not refresh and result_path.exists():
        try:
            return json.loads(result_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    pdf_path = uploads_dir / rec["storedName"]
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="File missing on disk")

    # Compute final result synchronously (single request), then cache.
    page_texts = extract_pages_best_effort(str(pdf_path))
    pages_for_schema = [(p.page_index, p.text) for p in page_texts if p.route == "text"]
    used_llm = False
    extracted_v2: ExtractedLabReportV2
    openai_configured = bool(os.getenv("OPENAI_API_KEY"))

    if openai_configured:
        try:
            extracted_v2 = extract_with_openai_two_pass(pages_for_schema)
            used_llm = True
        except Exception as e:
            extracted_v2 = extract_lab_schema_heuristic(pages_for_schema)
            extracted_v2.warnings.append(
                f"LLM extraction failed; fell back to heuristic: {type(e).__name__}"
            )
    else:
        extracted_v2 = extract_lab_schema_heuristic(pages_for_schema)
        extracted_v2.warnings.append("OPENAI_API_KEY not set; used heuristic extraction.")

    skipped_pages = [p.page_index for p in page_texts if p.route != "text"]
    if skipped_pages:
        extracted_v2.warnings.append(
            "Skipped pages with no visible/extractable text (OCR disabled): "
            + ", ".join([str(p + 1) for p in skipped_pages])
        )

    payload = {
        "fileId": file_id,
        "originalName": rec["originalName"],
        "extracted": _flatten_v2(extracted_v2),
        "extractedV2": extracted_v2.model_dump(),
        "pageRouting": [{"page": p.page_index, "route": p.route, "chars": len(p.text)} for p in page_texts],
        "llmUsed": used_llm,
        "extractedAt": datetime.now(timezone.utc).isoformat(),
    }

    result_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload

