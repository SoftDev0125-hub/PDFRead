from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


class Evidence(BaseModel):
    page: int | None = None
    snippet: str | None = None


class FieldValue(BaseModel):
    value: Any = None
    evidence: Evidence = Field(default_factory=Evidence)
    confidence: float | None = None  # 0..1 optional


class ExtractedAuthorizationV2(BaseModel):
    student_name: FieldValue = Field(default_factory=FieldValue)
    student_id: FieldValue = Field(default_factory=FieldValue)
    district: FieldValue = Field(default_factory=FieldValue)
    service_type: FieldValue = Field(default_factory=FieldValue)
    authorized_minutes: FieldValue = Field(default_factory=FieldValue)
    start_date: FieldValue = Field(default_factory=FieldValue)
    end_date: FieldValue = Field(default_factory=FieldValue)
    authorization_number: FieldValue = Field(default_factory=FieldValue)
    case_manager_name: FieldValue = Field(default_factory=FieldValue)
    subject_areas: FieldValue = Field(default_factory=FieldValue)
    notes: FieldValue = Field(default_factory=FieldValue)

    warnings: list[str] = Field(default_factory=list)
    validations: list[str] = Field(default_factory=list)


def _normalize_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def _normalize_name(s: str) -> str:
    s = _normalize_spaces(s)
    return s.title() if s.isupper() else s


def _pick_with_evidence(text: str, pattern: str, *, flags: int = re.IGNORECASE) -> tuple[str | None, str | None]:
    m = re.search(pattern, text, flags)
    if not m:
        return None, None
    val = _normalize_spaces(m.group(1))
    snippet = _normalize_spaces(m.group(0))
    return val, snippet


def _parse_mmddyy(s: str) -> date | None:
    s = _normalize_spaces(s)
    for fmt in ("%m/%d/%y", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _date_to_iso(d: date) -> str:
    return d.isoformat()


def extract_schema_from_pages(pages: list[tuple[int, str]]) -> ExtractedAuthorizationV2:
    """
    pages: list of (page_index, text)
    Heuristic schema extraction + evidence + validators.
    """
    joined = "\n\n".join([t for _, t in pages])
    out = ExtractedAuthorizationV2()

    # Student name + ID
    val, snip = _pick_with_evidence(joined, r"\bCLIENT INFORMATION\b[\s\S]{0,800}?\bNAME:\s*([A-Z][A-Z ,.'-]+)")
    if val:
        out.student_name.value = _normalize_name(val)
        out.student_name.evidence.snippet = snip
        out.student_name.confidence = 0.75

    val, snip = _pick_with_evidence(joined, r"\bCLIENT I\.D\.\s*:\s*([0-9A-Za-z-]+)")
    if val:
        out.student_id.value = val
        out.student_id.evidence.snippet = snip
        out.student_id.confidence = 0.8

    # Authorization number
    val, snip = _pick_with_evidence(joined, r"\bAUTHORIZATION\s*(?:No\.|NO\.|#)\s*:\s*([0-9A-Za-z-]+)")
    if val:
        out.authorization_number.value = val
        out.authorization_number.evidence.snippet = snip
        out.authorization_number.confidence = 0.85

    # Case manager
    val, snip = _pick_with_evidence(joined, r"\bCASEWORKER\s*:\s*([A-Z][A-Z ,.'-]+)")
    if val:
        out.case_manager_name.value = _normalize_name(val)
        out.case_manager_name.evidence.snippet = snip
        out.case_manager_name.confidence = 0.75

    # Service type
    val, snip = _pick_with_evidence(joined, r"\bSERVICE DETAILS\b[\s\S]{0,1200}?\n([A-Z][A-Z \-/]+)\n")
    if val:
        out.service_type.value = _normalize_spaces(val).upper()
        out.service_type.evidence.snippet = snip
        out.service_type.confidence = 0.6

    # Date range
    m = re.search(r"(\d{1,2}/\d{1,2}/\d{2,4})\s*(?:to|-|–)\s*(\d{1,2}/\d{1,2}/\d{2,4})", joined, re.IGNORECASE)
    if m:
        sd_raw, ed_raw = m.group(1), m.group(2)
        sd = _parse_mmddyy(sd_raw)
        ed = _parse_mmddyy(ed_raw)
        snippet = _normalize_spaces(m.group(0))
        if sd:
            out.start_date.value = _date_to_iso(sd)
            out.start_date.evidence.snippet = snippet
        if ed:
            out.end_date.value = _date_to_iso(ed)
            out.end_date.evidence.snippet = snippet
        if sd and ed and sd > ed:
            out.validations.append("start_date is after end_date")

    # Authorized minutes (derive from hours if only hours present)
    val, snip = _pick_with_evidence(joined, r"\b(\d+(?:\.\d+)?)\s*HRS\b")
    if val:
        try:
            mins = int(round(float(val) * 60))
            out.authorized_minutes.value = mins
            out.authorized_minutes.evidence.snippet = snip
            out.authorized_minutes.confidence = 0.4
            out.warnings.append("authorized_minutes derived from hours; may represent per-month or total.")
        except ValueError:
            out.warnings.append("Could not parse hours for authorized_minutes.")

    # Notes
    val, snip = _pick_with_evidence(
        joined,
        r"\bCOMMENTS:\s*(.+?)(?:\bGROSS AUTH\b|\bTOTAL\b|TERMS AND CONDITIONS)",
        flags=re.IGNORECASE | re.DOTALL,
    )
    if val:
        out.notes.value = _normalize_spaces(val)
        out.notes.evidence.snippet = _normalize_spaces(snip or "")
        out.notes.confidence = 0.55

    # Missing-field warnings (core set)
    core = [
        ("student_name", out.student_name.value),
        ("student_id", out.student_id.value),
        ("district", out.district.value),
        ("service_type", out.service_type.value),
        ("authorized_minutes", out.authorized_minutes.value),
        ("start_date", out.start_date.value),
        ("end_date", out.end_date.value),
        ("authorization_number", out.authorization_number.value),
        ("case_manager_name", out.case_manager_name.value),
        ("subject_areas", out.subject_areas.value),
    ]
    for k, v in core:
        if v in (None, "", []):
            out.warnings.append(f"Missing field: {k}")

    return out

