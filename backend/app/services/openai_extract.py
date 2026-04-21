from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI
from pydantic import ValidationError

from app.services.schema_extract import Evidence, ExtractedAuthorizationV2, FieldValue


REQUIRED_FIELDS: tuple[str, ...] = (
    "student_name",
    "student_id",
    "district",
    "service_type",
    "authorized_minutes",
    "start_date",
    "end_date",
    "authorization_number",
    "case_manager_name",
    "subject_areas",
    "notes",
)


def _client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    return OpenAI(api_key=api_key)


def _schema_prompt() -> str:
    return """You extract structured fields from authorization documents.

Return ONLY valid JSON matching this schema:
{
  "student_name": {"value": string|null, "evidence": {"page": number|null, "snippet": string|null}, "confidence": number|null},
  "student_id": {"value": string|null, "evidence": {"page": number|null, "snippet": string|null}, "confidence": number|null},
  "district": {"value": string|null, "evidence": {"page": number|null, "snippet": string|null}, "confidence": number|null},
  "service_type": {"value": string|null, "evidence": {"page": number|null, "snippet": string|null}, "confidence": number|null},
  "authorized_minutes": {"value": number|null, "evidence": {"page": number|null, "snippet": string|null}, "confidence": number|null},
  "start_date": {"value": string|null, "evidence": {"page": number|null, "snippet": string|null}, "confidence": number|null},
  "end_date": {"value": string|null, "evidence": {"page": number|null, "snippet": string|null}, "confidence": number|null},
  "authorization_number": {"value": string|null, "evidence": {"page": number|null, "snippet": string|null}, "confidence": number|null},
  "case_manager_name": {"value": string|null, "evidence": {"page": number|null, "snippet": string|null}, "confidence": number|null},
  "subject_areas": {"value": [string]|null, "evidence": {"page": number|null, "snippet": string|null}, "confidence": number|null},
  "notes": {"value": string|null, "evidence": {"page": number|null, "snippet": string|null}, "confidence": number|null},
  "warnings": [string],
  "validations": [string]
}

Rules:
- Evidence.page is 0-based page index when known; otherwise null.
- Evidence.snippet must be a short exact quote from the provided text (not invented).
- Dates must be ISO-8601 (YYYY-MM-DD) when possible; otherwise null + warning.
- authorized_minutes should be an integer number of minutes if you can infer it reliably; otherwise null.
- If a field is missing/unclear, set value null and add a warning like "Missing field: <field>" or "Ambiguous: <field>".
"""


def _make_pages_text(pages: list[tuple[int, str]]) -> str:
    parts: list[str] = []
    for idx, text in pages:
        parts.append(f"--- PAGE {idx} ---\n{text}")
    return "\n\n".join(parts)


def _coerce_to_v2(payload: dict[str, Any]) -> ExtractedAuthorizationV2:
    """
    Be forgiving: if the model omits some objects, fill them.
    """
    out = ExtractedAuthorizationV2()

    def get_field(name: str) -> FieldValue:
        raw = payload.get(name) or {}
        fv = FieldValue()
        fv.value = raw.get("value")
        ev = raw.get("evidence") or {}
        fv.evidence = Evidence(page=ev.get("page"), snippet=ev.get("snippet"))
        fv.confidence = raw.get("confidence")
        return fv

    for k in (
        "student_name",
        "student_id",
        "district",
        "service_type",
        "authorized_minutes",
        "start_date",
        "end_date",
        "authorization_number",
        "case_manager_name",
        "subject_areas",
        "notes",
    ):
        setattr(out, k, get_field(k))

    out.warnings = list(payload.get("warnings") or [])
    out.validations = list(payload.get("validations") or [])
    return out


def _call_openai_json(system: str, user: str) -> dict[str, Any]:
    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    c = _client()
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


def _missing_required_fields(v2: ExtractedAuthorizationV2) -> list[str]:
    missing: list[str] = []
    for k in REQUIRED_FIELDS:
        fv = getattr(v2, k)
        v = getattr(fv, "value", None)
        if v in (None, "", []):
            missing.append(k)
    return missing


def merge_v2(base: ExtractedAuthorizationV2, patch: ExtractedAuthorizationV2) -> ExtractedAuthorizationV2:
    """
    Merge patch into base for fields that are missing in base.
    Warnings/validations are concatenated (unique-ified).
    """
    out = base.model_copy(deep=True)
    for k in REQUIRED_FIELDS:
        bfv = getattr(out, k)
        if getattr(bfv, "value", None) not in (None, "", []):
            continue
        pfv = getattr(patch, k)
        if getattr(pfv, "value", None) in (None, "", []):
            continue
        setattr(out, k, pfv)

    def uniq(seq: list[str]) -> list[str]:
        seen: set[str] = set()
        res: list[str] = []
        for s in seq:
            if s in seen:
                continue
            seen.add(s)
            res.append(s)
        return res

    out.warnings = uniq((out.warnings or []) + (patch.warnings or []))
    out.validations = uniq((out.validations or []) + (patch.validations or []))
    return out


def extract_with_openai(pages: list[tuple[int, str]]) -> ExtractedAuthorizationV2:
    pages_text = _make_pages_text(pages)
    data = _call_openai_json(_schema_prompt(), pages_text)

    # Validate shape lightly by building our model.
    try:
        # Try strict validation if possible
        return ExtractedAuthorizationV2.model_validate(data)
    except ValidationError:
        return _coerce_to_v2(data)


def extract_with_openai_two_pass(pages: list[tuple[int, str]]) -> ExtractedAuthorizationV2:
    """
    Pass 1: full schema extraction.
    Pass 2: only ask for missing fields (targeted), then merge.
    """
    first = extract_with_openai(pages)
    missing = _missing_required_fields(first)
    if not missing:
        return first

    pages_text = _make_pages_text(pages)
    targeted_system = _schema_prompt() + "\n\nYou are doing a SECOND PASS. Focus ONLY on these fields:\n" + ", ".join(missing)
    targeted_user = (
        "Fill ONLY the missing fields listed by the system message. "
        "For fields you cannot find, keep value null and add/keep a warning.\n\n"
        + pages_text
    )

    data = _call_openai_json(targeted_system, targeted_user)
    try:
        second = ExtractedAuthorizationV2.model_validate(data)
    except ValidationError:
        second = _coerce_to_v2(data)

    merged = merge_v2(first, second)
    merged.warnings.append(f"Second-pass LLM attempted for missing: {', '.join(missing)}")
    return merged

