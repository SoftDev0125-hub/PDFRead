from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field


class Evidence(BaseModel):
    page: int | None = None
    snippet: str | None = None


class FieldValue(BaseModel):
    value: Any = None
    evidence: Evidence = Field(default_factory=Evidence)
    confidence: float | None = None  # 0..1 optional


BiomarkerStatus = Literal["optimal", "normal", "out_of_range", "unknown"]


class BiomarkerV2(BaseModel):
    name: FieldValue = Field(default_factory=FieldValue)  # standardized English name if possible
    original_name: FieldValue = Field(default_factory=FieldValue)

    value: FieldValue = Field(default_factory=FieldValue)  # numeric when possible; else string
    unit: FieldValue = Field(default_factory=FieldValue)  # standardized English unit when possible

    reference_range_text: FieldValue = Field(default_factory=FieldValue)  # e.g. "70-99" or "< 5.0"
    status: FieldValue = Field(default_factory=FieldValue)  # BiomarkerStatus

    notes: FieldValue = Field(default_factory=FieldValue)  # e.g. "H", "L", "flagged", "fasting"


class ExtractedLabReportV2(BaseModel):
    patient_name: FieldValue = Field(default_factory=FieldValue)
    age_years: FieldValue = Field(default_factory=FieldValue)
    sex: FieldValue = Field(default_factory=FieldValue)  # "male" | "female" | other text

    report_date: FieldValue = Field(default_factory=FieldValue)  # ISO-8601 when possible
    source: FieldValue = Field(default_factory=FieldValue)  # lab/vendor name if present

    biomarkers: list[BiomarkerV2] = Field(default_factory=list)

    warnings: list[str] = Field(default_factory=list)
    validations: list[str] = Field(default_factory=list)


def _normalize_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def extract_lab_schema_heuristic(pages: list[tuple[int, str]]) -> ExtractedLabReportV2:
    """
    Best-effort heuristic extraction when no LLM is configured.
    This intentionally aims for *some* biomarker rows rather than perfection.
    """
    joined = "\n\n".join([t for _, t in pages])
    out = ExtractedLabReportV2()

    # Age / sex (common patterns; may vary heavily by vendor)
    m_age = re.search(r"\bAge\b\s*[:\-]?\s*(\d{1,3})\b", joined, re.IGNORECASE)
    if m_age:
        out.age_years.value = int(m_age.group(1))
        out.age_years.evidence.snippet = _normalize_spaces(m_age.group(0))
        out.age_years.confidence = 0.5
    m_sex = re.search(r"\bSex\b\s*[:\-]?\s*(Male|Female|M|F)\b", joined, re.IGNORECASE)
    if m_sex:
        raw = m_sex.group(1)
        norm = "male" if raw.lower() in ("m", "male") else "female" if raw.lower() in ("f", "female") else raw
        out.sex.value = norm
        out.sex.evidence.snippet = _normalize_spaces(m_sex.group(0))
        out.sex.confidence = 0.5

    # Biomarker rows: try to capture common "NAME  VALUE  UNIT  RANGE" patterns per line.
    # Example: "Glucose  92  mg/dL  70-99"
    line_re = re.compile(
        r"^(?!\s*(?:page|patient|name|date|reported|collected)\b)"
        r"(?P<name>[A-Za-z][A-Za-z0-9 \-()/%,.+]{1,80}?)\s+"
        r"(?P<value>[<>≤≥]?\s*[-+]?\d+(?:\.\d+)?(?:e[-+]?\d+)?)\s*"
        r"(?P<unit>[A-Za-z/%µμ][A-Za-z0-9/%µμ\-\^]*)?\s*"
        r"(?P<range>(?:<|>|≤|≥)?\s*[-+]?\d+(?:\.\d+)?(?:\s*(?:-|–|to)\s*[-+]?\d+(?:\.\d+)?)?)?\s*$",
        flags=re.IGNORECASE,
    )
    for page_idx, text in pages:
        for raw_line in (text or "").splitlines():
            line = raw_line.rstrip()
            if len(line) < 6:
                continue
            m = line_re.match(line)
            if not m:
                continue
            name = _normalize_spaces(m.group("name"))
            value = m.group("value")
            unit = (m.group("unit") or "").strip() or None
            rtxt = _normalize_spaces(m.group("range") or "") or None

            b = BiomarkerV2()
            b.original_name.value = name
            b.original_name.evidence = Evidence(page=page_idx, snippet=_normalize_spaces(line)[:220])
            b.original_name.confidence = 0.35
            b.name.value = name  # no standardization without LLM
            b.name.evidence = b.original_name.evidence
            b.name.confidence = 0.2

            try:
                b.value.value = float(value) if "." in value else int(value)
            except Exception:
                b.value.value = value
            b.value.evidence = b.original_name.evidence
            b.value.confidence = 0.35

            b.unit.value = unit
            b.unit.evidence = b.original_name.evidence
            b.unit.confidence = 0.25

            b.reference_range_text.value = rtxt
            b.reference_range_text.evidence = b.original_name.evidence
            b.reference_range_text.confidence = 0.2

            b.status.value = "unknown"
            b.status.confidence = 0.0
            out.biomarkers.append(b)

    if not out.biomarkers:
        out.warnings.append("No biomarker rows detected by heuristics; configure OPENAI_API_KEY for robust extraction.")

    return out

