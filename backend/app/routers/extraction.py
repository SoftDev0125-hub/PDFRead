from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.services.pdf_text import extract_pdf_text


router = APIRouter(tags=["extraction"])


class ExtractedAuthorization(BaseModel):
    student_name: str | None = None
    student_id: str | None = None
    district: str | None = None
    service_type: str | None = None
    authorized_minutes: int | None = None
    start_date: str | None = None
    end_date: str | None = None
    authorization_number: str | None = None
    case_manager_name: str | None = None
    subject_areas: list[str] | None = None
    notes: str | None = None

    warnings: list[str] = []


def _uploads_dir(request: Request) -> Path:
    return request.app.state.uploads_dir  # type: ignore[attr-defined]


def _results_dir(request: Request) -> Path:
    return request.app.state.results_dir  # type: ignore[attr-defined]


def _load_meta(uploads_dir: Path) -> dict[str, Any]:
    p = uploads_dir / "_meta.json"
    if not p.exists():
        return {"files": []}
    return json.loads(p.read_text(encoding="utf-8"))


def _normalize_name(s: str) -> str:
    s = re.sub(r"\s+", " ", s.strip())
    return s.title() if s.isupper() else s


def _hours_to_minutes(hours: float) -> int:
    return int(round(hours * 60))


def _heuristic_extract(text: str) -> ExtractedAuthorization:
    warnings: list[str] = []
    cleaned = re.sub(r"[ \t]+", " ", text)

    def pick(pattern: str, flags: int = re.IGNORECASE) -> str | None:
        m = re.search(pattern, cleaned, flags)
        return m.group(1).strip() if m else None

    # Common patterns seen in the sample PDF you shared
    student_name = pick(r"\bCLIENT INFORMATION\b.*?\bNAME:\s*([A-Z][A-Z ,.'-]+)", flags=re.IGNORECASE | re.DOTALL)
    if student_name:
        student_name = _normalize_name(student_name)

    student_id = pick(r"\bCLIENT I\.D\.\s*:\s*([0-9A-Za-z-]+)")
    authorization_number = pick(r"\bAUTHORIZATION\s*(?:No\.|NO\.|#)\s*:\s*([0-9A-Za-z-]+)")
    case_manager_name = pick(r"\bCASEWORKER\s*:\s*([A-Z][A-Z ,.'-]+)")
    if case_manager_name:
        case_manager_name = _normalize_name(case_manager_name)

    # Service type: use the first all-caps service line under SERVICE DETAILS if present
    service_type = pick(r"\bSERVICE DETAILS\b.*?\n([A-Z][A-Z \-/]+)\n", flags=re.IGNORECASE | re.DOTALL)
    if service_type:
        service_type = re.sub(r"\s+", " ", service_type).strip().upper()

    # Date range: "09/01/26 to 12/31/26" (accepts separators)
    date_range = pick(r"(\d{1,2}/\d{1,2}/\d{2,4})\s*(?:to|-|–)\s*(\d{1,2}/\d{1,2}/\d{2,4})", flags=re.IGNORECASE)
    start_date = end_date = None
    if date_range:
        # pick() returns group(1) only; do full match for two groups
        m = re.search(r"(\d{1,2}/\d{1,2}/\d{2,4})\s*(?:to|-|–)\s*(\d{1,2}/\d{1,2}/\d{2,4})", cleaned)
        if m:
            start_date, end_date = m.group(1), m.group(2)

    # Authorized hours: "30.00 HRS-DIR" or "30 HRS/MO"
    authorized_minutes: int | None = None
    hrs = pick(r"\b(\d+(?:\.\d+)?)\s*HRS\b")
    if hrs:
        try:
            authorized_minutes = _hours_to_minutes(float(hrs))
            warnings.append("authorized_minutes derived from hours; confirm meaning (per month vs total).")
        except ValueError:
            warnings.append("Could not parse hours value.")

    notes = pick(r"\bCOMMENTS:\s*(.+?)(?:\bGROSS AUTH\b|\bTOTAL\b|TERMS AND CONDITIONS)", flags=re.IGNORECASE | re.DOTALL)
    if notes:
        notes = notes.strip().replace("\n", " ")

    out = ExtractedAuthorization(
        student_name=student_name,
        student_id=student_id,
        district=None,
        service_type=service_type,
        authorized_minutes=authorized_minutes,
        start_date=start_date,
        end_date=end_date,
        authorization_number=authorization_number,
        case_manager_name=case_manager_name,
        subject_areas=None,
        notes=notes,
        warnings=warnings,
    )

    for field in (
        "student_name",
        "student_id",
        "service_type",
        "start_date",
        "end_date",
        "authorization_number",
        "case_manager_name",
    ):
        if getattr(out, field) in (None, "", []):
            out.warnings.append(f"Missing field: {field}")

    if out.district is None:
        out.warnings.append("Missing field: district (often not explicit in PDFs).")
    if out.subject_areas is None:
        out.warnings.append("Missing field: subject_areas (may not exist in some PDFs).")

    return out


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

    text = extract_pdf_text(pdf_path)
    extracted = _heuristic_extract(text)

    payload = {
        "fileId": file_id,
        "originalName": rec["originalName"],
        "extracted": extracted.model_dump(),
        "extractedAt": datetime.now(timezone.utc).isoformat(),
    }

    (results_dir / f"{file_id}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload

