from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date
from typing import Any

import gspread


@dataclass(frozen=True)
class SheetsConfig:
    spreadsheet_id: str
    worksheet_name: str


def _load_service_account() -> dict[str, Any]:
    raw = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not raw:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON is not set")

    raw = raw.strip()
    # Allow either a file path or inline JSON
    if raw.startswith("{"):
        return json.loads(raw)
    return json.loads(open(raw, "r", encoding="utf-8").read())


def _config() -> SheetsConfig:
    sid = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID")
    wname = os.getenv("GOOGLE_SHEETS_WORKSHEET", "Sheet1")
    if not sid:
        raise RuntimeError("GOOGLE_SHEETS_SPREADSHEET_ID is not set")
    return SheetsConfig(spreadsheet_id=sid, worksheet_name=wname)


def _client() -> gspread.Client:
    sa = _load_service_account()
    return gspread.service_account_from_dict(sa)


def _iso_to_mmddyy(iso_date: str | None) -> str | None:
    if not iso_date:
        return None
    # Accept YYYY-MM-DD; if already MM/DD/YY-ish, return as-is.
    s = str(iso_date).strip()
    if "/" in s:
        return s
    try:
        y, m, d = s.split("-", 2)
        return f"{int(m):02d}/{int(d):02d}/{y[-2:]}"
    except Exception:
        return s


def _service_window(start_iso: str | None, end_iso: str | None) -> str | None:
    s = _iso_to_mmddyy(start_iso)
    e = _iso_to_mmddyy(end_iso)
    if s and e:
        return f"{s} - {e}"
    return s or e


def _hours_per_month_text(authorized_minutes: Any, start_iso: str | None, end_iso: str | None) -> str | None:
    """
    Training guide: monthly hours plus service dates in parentheses.
    """
    if authorized_minutes is None:
        return None
    try:
        mins = int(authorized_minutes)
    except Exception:
        base = str(authorized_minutes)
    else:
        if mins % 60 == 0:
            hrs = mins // 60
            base = f"{hrs} hours a month"
        else:
            base = f"{mins} minutes a month"
    window = _service_window(start_iso, end_iso)
    if window:
        return f"{base} ({window})"
    return base


def _build_auth_comments(extracted_flat: dict[str, Any], meta: dict[str, Any] | None = None) -> str:
    """
    Mirrors data-entry training: new line at bottom with *date received*, then body text.
    We substitute coordinator email with structured extraction + file reference.
    """
    parts: list[str] = []
    recv = (meta or {}).get("receivedAt")
    recv_day = str(recv)[:10] if recv else date.today().isoformat()
    parts.append(_iso_to_mmddyy(recv_day) or "")
    parts.append(
        " | ".join(
            [
                f"auth# {extracted_flat.get('authorization_number') or '—'}",
                f"svc {extracted_flat.get('service_type') or '—'}",
                f"district {extracted_flat.get('district') or '—'}",
            ]
        )
    )
    if meta:
        parts.append(f"POS / file: {meta.get('originalName')}")
        parts.append(f"upload fileId: {meta.get('fileId')}")
    warns = extracted_flat.get("warnings") or []
    if warns:
        parts.append("warnings: " + "; ".join([str(w) for w in warns]))
    return "\n".join(parts)


MASTERFILE_HEADERS: list[str] = [
    "UCI",
    "Student",
    "Guardian Name",
    "CL Director",
    "Spanish",
    "Category",
    "Assessment",
    "Authorization Comments",
    "Contract Service Date 1st Auth",
    "2nd Authorization",
    "3rd Authorization",
    "4th Authorization",
    "Current Auth Expiration Date Format: MM/DD/YY",
    "Requested Authorization (Pending)",
    "Hours Per Month",
    "Upcoming Renewal Status",
    "Summer",
    "Authorization Status",
    "SC\n(First Name Last Name)",
    "Student status",
    "Pending Confirmation",
    "Hard to Contact",
    "Requested Schedule",
    "Areas of Support",
    "Parent Requested Mode of Services",
    "Virtual Tutor List",
    "Current Virtual Tutor",
    "In Home Tutor List",
    "Current In Home Tutor",
    "Additional Notes",
    "Parent Feedback",
    "Parent Feedback (orginal AG)",
    "Start Date Track",
    "Validation: CONCAT Service Dates",
    "Validation: Contract Service Date",
    "Validation: Current Auth Expiration Date",
    "Validation:\nService Date = Expiration Date",
    "Standardized SC Names",
]


def _find_header_row(ws: Any) -> int | None:
    # Look for the "UCI" header near the top of the sheet (one row fetch per scan row).
    max_scan_rows = min(ws.row_count, 40)
    for r in range(1, max_scan_rows + 1):
        row = ws.row_values(r)
        for v in row:
            if v is not None and str(v).strip() == "UCI":
                return r
    return None


def _read_header_map(ws: Any, header_row: int) -> dict[str, int]:
    headers = ws.row_values(header_row)
    m: dict[str, int] = {}
    for idx, h in enumerate(headers, start=1):
        if h is None:
            continue
        key = str(h).strip()
        if key:
            m[key] = idx
    return m


def append_masterfile_row(extracted_flat: dict[str, Any], meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Append a row aligned to the Tutor Me masterfile columns (as shown in the provided example sheet).

    Mapping (best-effort, conservative):
    - UCI <- student_id
    - Student <- student_name
    - Authorization Comments <- structured extraction log + warnings
    - Contract Service Date 1st Auth <- start-end window (MM/DD/YY)
    - Current Auth Expiration Date Format: MM/DD/YY <- end date
    - Hours Per Month <- derived text from authorized_minutes
    - Areas of Support <- subject_areas (comma-separated) or service_type
    - Additional Notes <- notes
    - Authorization Status <- "Received" (POS uploaded into tool)
    - Spanish <- FALSE (matches example sheet convention)
    """
    cfg = _config()
    client = _client()
    sh = client.open_by_key(cfg.spreadsheet_id)
    ws = sh.worksheet(cfg.worksheet_name)

    header_row = _find_header_row(ws)
    if header_row is None:
        ws.append_row(MASTERFILE_HEADERS, value_input_option="USER_ENTERED")
        header_row = _find_header_row(ws)
    if header_row is None:
        raise RuntimeError("Could not locate masterfile header row (expected a column titled UCI)")

    col = _read_header_map(ws, header_row)

    subject_areas = extracted_flat.get("subject_areas")
    if isinstance(subject_areas, list):
        areas = ", ".join([str(x) for x in subject_areas if x is not None])
    else:
        areas = str(subject_areas) if subject_areas is not None else ""

    row_len = max(col.values()) if col else len(MASTERFILE_HEADERS)
    row = ["" for _ in range(row_len)]

    def set_cell(header: str, value: Any) -> None:
        if header not in col:
            return
        i = col[header] - 1
        if i < 0 or i >= len(row):
            return
        row[i] = "" if value is None else value

    set_cell("UCI", extracted_flat.get("student_id"))
    set_cell("Student", extracted_flat.get("student_name"))
    set_cell("Spanish", False)
    set_cell("Authorization Comments", _build_auth_comments(extracted_flat, meta))
    set_cell("Contract Service Date 1st Auth", _service_window(extracted_flat.get("start_date"), extracted_flat.get("end_date")))
    set_cell("Current Auth Expiration Date Format: MM/DD/YY", _iso_to_mmddyy(extracted_flat.get("end_date")))
    set_cell(
        "Hours Per Month",
        _hours_per_month_text(
            extracted_flat.get("authorized_minutes"),
            extracted_flat.get("start_date"),
            extracted_flat.get("end_date"),
        ),
    )
    set_cell("Authorization Status", "Received")
    set_cell("SC\n(First Name Last Name)", extracted_flat.get("case_manager_name"))
    set_cell("Areas of Support", areas or extracted_flat.get("service_type") or "")
    set_cell("Additional Notes", extracted_flat.get("notes") or "")

    ws.append_row(row, value_input_option="USER_ENTERED")
    return {
        "ok": True,
        "spreadsheetId": cfg.spreadsheet_id,
        "worksheet": cfg.worksheet_name,
        "headerRow": header_row,
        "mode": "masterfile",
    }


def append_authorization_row(extracted_flat: dict[str, Any], meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Backwards-compatible name: now writes the masterfile-shaped row.
    """
    return append_masterfile_row(extracted_flat, meta=meta)
