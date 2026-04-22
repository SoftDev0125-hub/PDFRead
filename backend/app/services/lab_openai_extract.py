from __future__ import annotations

import json
import os
import re
from typing import Any

from openai import OpenAI
from pydantic import ValidationError

from app.services.lab_schema import BiomarkerV2, Evidence, ExtractedLabReportV2, FieldValue


def _client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    return OpenAI(api_key=api_key)


def _make_pages_text(pages: list[tuple[int, str]]) -> str:
    """
    Accuracy-first extraction input:
    - We MUST not drop biomarker rows.
    - We still avoid sending irrelevant boilerplate by extracting:
      - a small header slice from each page (demographics/report metadata)
      - all lines that look like analyte/result rows
      - a small amount of context around those rows
    """
    # "Row-ish": analyte name + value (supports <, >, scientific notation).
    rowish_re = re.compile(
        r"^[A-Za-z][A-Za-z0-9 \-()/%,.+]{2,80}\s+"
        r"(?:[<>≤≥]?\s*)?"
        r"[-+]?\d+(?:\.\d+)?(?:e[-+]?\d+)?"
        r"(?:\s*[A-Za-z/%µμ][A-Za-z0-9/%µμ\-\^]*)?"
        r"(?:\s+(?:<|>|≤|≥)?\s*[-+]?\d+(?:\.\d+)?(?:\s*(?:-|–|to)\s*[-+]?\d+(?:\.\d+)?)?)?"
        r"\s*$",
        re.IGNORECASE,
    )
    header_keep_re = re.compile(
        r"(?i)\b(age|sex|gender|dob|date of birth|patient|name|collected|received|reported|reference|range|unit|lab)\b"
    )

    header_lines_per_page = 30
    context_radius = 2
    max_rows_total = 1200  # cap safety; should cover typical reports

    parts: list[str] = []
    rows_kept = 0

    for idx, text in pages:
        lines = (text or "").splitlines()
        if not lines:
            continue

        hit_idxs: set[int] = set()

        # Keep header slice (metadata/demographics), but only meaningful lines.
        for i in range(min(header_lines_per_page, len(lines))):
            l = lines[i].strip()
            if not l:
                continue
            if header_keep_re.search(l) or len(l) < 120:
                hit_idxs.add(i)

        # Keep ALL detected biomarker/result rows + context around them.
        for i, raw in enumerate(lines):
            l = raw.strip()
            if not l:
                continue
            if rowish_re.match(l):
                for j in range(max(0, i - context_radius), min(len(lines), i + context_radius + 1)):
                    hit_idxs.add(j)
                rows_kept += 1
                if rows_kept >= max_rows_total:
                    break

        selected = [lines[i] for i in sorted(hit_idxs)]
        if selected:
            parts.append(f"--- PAGE {idx} ---\n" + "\n".join(selected))
        if rows_kept >= max_rows_total:
            break

    # If we failed to detect any rows (likely an unusual layout), fall back to full text.
    if rows_kept == 0:
        return "\n\n".join([f"--- PAGE {idx} ---\n{text}" for idx, text in pages])

    return "\n\n".join(parts)


def _schema_prompt() -> str:
    return """You extract data from lab test reports (PDF text/OCR).

Goal:
- Extract patient demographics (age, sex) as shown in the report.
- Extract ALL available biomarkers / analytes from the report (do not omit rows).
- Standardize biomarker names and units into English when possible.
- Classify each biomarker result as: "optimal", "normal", or "out_of_range".

IMPORTANT classification rules:
- Use the reference ranges / flags as presented in the report for THIS patient’s age and sex.
- If the report only provides a single reference interval (no explicit "optimal" range), use:
  - "normal" when the value is within the provided interval/threshold
  - "out_of_range" when it is outside
  - "optimal" ONLY when the report explicitly provides an optimal/desired/goal range or clearly labels the result as optimal.
- If you cannot determine status reliably, set status to "unknown" and add a warning.

Return ONLY valid JSON matching this schema:
{
  "patient_name": {"value": string|null, "evidence": {"page": number|null, "snippet": string|null}, "confidence": number|null},
  "age_years": {"value": number|null, "evidence": {"page": number|null, "snippet": string|null}, "confidence": number|null},
  "sex": {"value": string|null, "evidence": {"page": number|null, "snippet": string|null}, "confidence": number|null},
  "report_date": {"value": string|null, "evidence": {"page": number|null, "snippet": string|null}, "confidence": number|null},
  "source": {"value": string|null, "evidence": {"page": number|null, "snippet": string|null}, "confidence": number|null},
  "biomarkers": [
    {
      "name": {"value": string|null, "evidence": {"page": number|null, "snippet": string|null}, "confidence": number|null},
      "original_name": {"value": string|null, "evidence": {"page": number|null, "snippet": string|null}, "confidence": number|null},
      "value": {"value": number|string|null, "evidence": {"page": number|null, "snippet": string|null}, "confidence": number|null},
      "unit": {"value": string|null, "evidence": {"page": number|null, "snippet": string|null}, "confidence": number|null},
      "reference_range_text": {"value": string|null, "evidence": {"page": number|null, "snippet": string|null}, "confidence": number|null},
      "status": {"value": "optimal"|"normal"|"out_of_range"|"unknown"|null, "evidence": {"page": number|null, "snippet": string|null}, "confidence": number|null},
      "notes": {"value": string|null, "evidence": {"page": number|null, "snippet": string|null}, "confidence": number|null}
    }
  ],
  "warnings": [string],
  "validations": [string]
}

Evidence rules:
- Evidence.page is 0-based page index when known; otherwise null.
- Evidence.snippet is optional; ONLY include snippets for patient_name, age_years, sex, report_date, and source.
- For biomarkers, set evidence.page/snippet to null unless it is trivially available (this keeps responses smaller and faster).

Data rules:
- age_years should be a number if possible.
- report_date should be ISO-8601 (YYYY-MM-DD) when possible; otherwise keep the original string and add a warning.
- If a biomarker row repeats on multiple pages, keep the most complete one (or include duplicates only if clearly distinct panels).
- If you see a lab table row that looks like an analyte + result, include it even if unit/range is missing.
"""


def _call_openai_json(system: str, user: str) -> dict[str, Any]:
    """
    Uses the Responses API and streams server-side for lower end-to-end latency,
    but buffers and returns only after the full JSON is complete (UI remains all-at-once).
    Falls back to chat.completions if streaming isn't available.
    """
    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    c = _client()

    # Default on: streaming reduces "idle waiting" on long responses.
    streaming_enabled = os.getenv("OPENAI_STREAMING", "1").strip().lower() not in ("0", "false", "no", "off")

    if streaming_enabled:
        try:
            # Newer OpenAI python SDKs support response streaming via client.responses.create(..., stream=True).
            text_parts: list[str] = []
            stream = c.responses.create(
                model=model,
                temperature=0,
                response_format={"type": "json_object"},
                input=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                stream=True,
            )

            for event in stream:
                # Best-effort: handle different SDK event shapes.
                et = getattr(event, "type", None) or (event.get("type") if isinstance(event, dict) else None)
                if et in ("response.output_text.delta", "response.output_text.annotation"):
                    delta = getattr(event, "delta", None) or (event.get("delta") if isinstance(event, dict) else None)
                    if isinstance(delta, str) and delta:
                        text_parts.append(delta)
                elif et == "response.completed":
                    break

            content = "".join(text_parts).strip() or "{}"
            return json.loads(content)
        except Exception:
            # Fall back below.
            pass

    resp = c.chat.completions.create(
        model=model,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    content = resp.choices[0].message.content or "{}"
    return json.loads(content)


def _coerce_field(raw: Any) -> FieldValue:
    fv = FieldValue()
    if isinstance(raw, dict):
        fv.value = raw.get("value")
        ev = raw.get("evidence") or {}
        fv.evidence = Evidence(page=ev.get("page"), snippet=ev.get("snippet"))
        fv.confidence = raw.get("confidence")
    else:
        fv.value = raw
    return fv


def _coerce_to_v2(payload: dict[str, Any]) -> ExtractedLabReportV2:
    out = ExtractedLabReportV2()
    for k in ("patient_name", "age_years", "sex", "report_date", "source"):
        setattr(out, k, _coerce_field(payload.get(k)))
    out.warnings = list(payload.get("warnings") or [])
    out.validations = list(payload.get("validations") or [])

    bios: list[BiomarkerV2] = []
    for raw in list(payload.get("biomarkers") or []):
        if not isinstance(raw, dict):
            continue
        b = BiomarkerV2()
        for k in ("name", "original_name", "value", "unit", "reference_range_text", "status", "notes"):
            setattr(b, k, _coerce_field(raw.get(k)))
        bios.append(b)
    out.biomarkers = bios
    return out


def extract_with_openai(pages: list[tuple[int, str]]) -> ExtractedLabReportV2:
    pages_text = _make_pages_text(pages)
    data = _call_openai_json(_schema_prompt(), pages_text)
    try:
        return ExtractedLabReportV2.model_validate(data)
    except ValidationError:
        return _coerce_to_v2(data)


def extract_with_openai_two_pass(pages: list[tuple[int, str]]) -> ExtractedLabReportV2:
    """
    Pass 1: full extraction.
    Pass 2: ask only for missing/empty essentials and any missing biomarker fields.
    """
    first = extract_with_openai(pages)

    missing_core: list[str] = []
    for k in ("age_years", "sex"):
        v = getattr(first, k).value
        if v in (None, "", []):
            missing_core.append(k)

    # Skip the second pass unless we are truly missing key demographics OR got no biomarkers.
    if not missing_core and first.biomarkers:
        return first

    pages_text = _make_pages_text(pages)
    targeted_system = _schema_prompt() + "\n\nYou are doing a SECOND PASS. Focus on: " + ", ".join(
        ["age_years", "sex", "biomarkers"]
    )
    targeted_user = (
        "Fill missing demographic fields (age_years, sex) and ensure ALL biomarker rows are captured. "
        "If uncertain, set fields to null and add warnings.\n\n" + pages_text
    )
    data = _call_openai_json(targeted_system, targeted_user)
    try:
        second = ExtractedLabReportV2.model_validate(data)
    except ValidationError:
        second = _coerce_to_v2(data)

    # Merge: keep first's core if present; union biomarkers by standardized name+unit+value string
    merged = first.model_copy(deep=True)
    for k in ("patient_name", "age_years", "sex", "report_date", "source"):
        if getattr(merged, k).value in (None, "", []):
            setattr(merged, k, getattr(second, k))

    def biomarker_key(b: BiomarkerV2) -> str:
        n = str((b.name.value or b.original_name.value or "")).strip().casefold()
        u = str((b.unit.value or "")).strip().casefold()
        v = str((b.value.value if b.value.value is not None else "")).strip().casefold()
        return f"{n}|{u}|{v}"

    seen: set[str] = set()
    out_bios: list[BiomarkerV2] = []
    for b in list(merged.biomarkers) + list(second.biomarkers):
        k = biomarker_key(b)
        if not k.strip("|"):
            continue
        if k in seen:
            continue
        seen.add(k)
        out_bios.append(b)
    merged.biomarkers = out_bios

    def uniq(seq: list[str]) -> list[str]:
        seen2: set[str] = set()
        res: list[str] = []
        for s in seq:
            if s in seen2:
                continue
            seen2.add(s)
            res.append(s)
        return res

    merged.warnings = uniq((merged.warnings or []) + (second.warnings or []))
    merged.validations = uniq((merged.validations or []) + (second.validations or []))
    merged.warnings.append("Second-pass LLM attempted to improve demographics/biomarkers coverage.")
    return merged

