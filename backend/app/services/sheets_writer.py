from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import gspread
from gspread.utils import rowcol_to_a1


@dataclass(frozen=True)
class SheetsConfig:
    spreadsheet_id: str
    worksheet_name: str
    # worksheet_gid: optional URL `gid` (sheetId); when set, used instead of worksheet_name to select the tab.
    worksheet_gid: int | None = None


def _resolve_sa_json_path(raw_path: str) -> Path:
    """Resolve service-account JSON path even when cwd is not `backend/`."""
    p = Path(raw_path)
    if p.is_file():
        return p.resolve()
    backend_dir = Path(__file__).resolve().parents[2]
    candidates = [
        backend_dir / raw_path,
        backend_dir.parent / raw_path,
        Path.cwd() / raw_path,
    ]
    for c in candidates:
        try:
            if c.is_file():
                return c.resolve()
        except OSError:
            continue
    raise FileNotFoundError(f"Service account JSON not found (tried cwd, backend/, repo root): {raw_path}")


def _load_service_account() -> dict[str, Any]:
    raw = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not raw:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON is not set")

    raw = raw.strip()
    # Allow either a file path or inline JSON
    if raw.startswith("{"):
        return json.loads(raw)
    path = _resolve_sa_json_path(raw)
    return json.loads(path.read_text(encoding="utf-8"))


def _config() -> SheetsConfig:
    sid = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID")
    wname = os.getenv("GOOGLE_SHEETS_WORKSHEET", "Sheet1")
    if not sid:
        raise RuntimeError("GOOGLE_SHEETS_SPREADSHEET_ID is not set")
    gid_raw = (os.getenv("GOOGLE_SHEETS_WORKSHEET_ID") or "").strip()
    worksheet_gid: int | None = None
    if gid_raw:
        try:
            worksheet_gid = int(gid_raw)
        except ValueError:
            worksheet_gid = None
    return SheetsConfig(spreadsheet_id=sid, worksheet_name=wname, worksheet_gid=worksheet_gid)


def _client() -> gspread.Client:
    sa = _load_service_account()
    return gspread.service_account_from_dict(sa)


def troubleshooting_for_sheets_permission_denied() -> dict[str, Any]:
    """
    When Sheets returns 403 on writes, the spreadsheet often opens fine in read-only mode
    (e.g. "Anyone with the link" as Viewer) but the service account is not an Editor.
    """
    email: str | None = None
    try:
        raw_email = _load_service_account().get("client_email")
        email = str(raw_email) if raw_email else None
    except Exception:
        pass

    steps: list[str] = [
        "The spreadsheet ID is valid and can be opened, but Google rejected changing cells. "
        "That usually means this automation account is not allowed to edit the file.",
    ]
    if email:
        steps.extend(
            [
                f"In Google Sheets: Share -> add this address exactly -> role Editor: {email}",
                "Viewer or Commenter is not enough; the app must append or update rows.",
                'Link sharing set to "Anyone with the link" (view only) does not give this account edit access; invite the address above explicitly.',
            ]
        )
    else:
        steps.append("Fix GOOGLE_SERVICE_ACCOUNT_JSON so the key loads; then use the client_email inside that JSON when sharing.")

    steps.extend(
        [
            "In Google Cloud Console for the project that owns this key: APIs and Services -> Library -> enable Google Sheets API (enable Google Drive API as well if problems persist).",
            "On Google Workspace, domain policy may block sharing with @...iam.gserviceaccount.com; an admin may need to allow it or use a sheet owned outside the restriction.",
        ]
    )
    return {"serviceAccountEmail": email, "steps": steps}


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
    max_scan_rows = min(ws.row_count, 120)
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


_AUTH_DATE_HEADERS: tuple[str, ...] = (
    "Contract Service Date 1st Auth",
    "2nd Authorization",
    "3rd Authorization",
    "4th Authorization",
)


def _find_matching_data_row(
    ws: Any, header_row: int, col: dict[str, int], student_id: Any, student_name: Any
) -> int | None:
    """Training guide step 3: locate the student's row by UCI (preferred) or Student name."""
    uci_col = col.get("UCI")
    stu_col = col.get("Student")
    if not uci_col and not stu_col:
        return None
    c_min = min(c for c in (uci_col, stu_col) if c)
    c_max = max(c for c in (uci_col, stu_col) if c)
    last_r = min(ws.row_count, header_row + 2500)
    if last_r <= header_row:
        return None
    rng = f"{rowcol_to_a1(header_row + 1, c_min)}:{rowcol_to_a1(last_r, c_max)}"
    data = ws.get(rng) or []

    def at(row_vals: list[Any], abs_c: int) -> Any:
        idx = abs_c - c_min
        if idx < 0 or idx >= len(row_vals):
            return None
        return row_vals[idx]

    sid = str(student_id).strip() if student_id is not None and str(student_id).strip() else ""
    sname = str(student_name).strip() if student_name is not None and str(student_name).strip() else ""
    sname_key = re.sub(r"\s+", " ", sname).casefold() if sname else ""

    for i, row in enumerate(data):
        rnum = header_row + 1 + i
        if not isinstance(row, list):
            row = []
        if sid and uci_col:
            uci_v = at(row, uci_col)
            if uci_v is not None and str(uci_v).strip() == sid:
                return rnum
        if sname_key and stu_col:
            name_v = at(row, stu_col)
            if name_v is not None and re.sub(r"\s+", " ", str(name_v).strip()).casefold() == sname_key:
                return rnum
    return None


def _first_empty_auth_date_col(ws: Any, row: int, col: dict[str, int]) -> int | None:
    """Pick 1st/2nd/3rd/4th auth date column per training guide step 7 (first empty slot)."""
    for h in _AUTH_DATE_HEADERS:
        if h not in col:
            continue
        c = col[h]
        v = ws.cell(row, c).value
        if v is None or str(v).strip() == "":
            return c
    for h in reversed(_AUTH_DATE_HEADERS):
        if h in col:
            return col[h]
    return None


def append_masterfile_row(extracted_flat: dict[str, Any], meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Sync extraction into the Tutor Me masterfile (per Auth Data Entry Training Guide).

    When a row exists for the same **UCI** or **Student** name, that row is **updated**:
    append to **Authorization Comments** (date + structured log), fill the next open
    **Contract Service Date** slot (1st / 2nd / 3rd / 4th), refresh expiration, hours,
    areas, status (**Received** when a POS PDF is processed here), and append **Additional Notes**.

    If no matching row is found, a **new row** is appended at the bottom.
    """
    cfg = _config()
    client = _client()
    sh = client.open_by_key(cfg.spreadsheet_id)
    if cfg.worksheet_gid is not None:
        ws = sh.get_worksheet_by_id(cfg.worksheet_gid)
    else:
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

    sid = extracted_flat.get("student_id")
    sname = extracted_flat.get("student_name")
    match_row = _find_matching_data_row(ws, header_row, col, sid, sname)

    auth_comments_block = _build_auth_comments(extracted_flat, meta)
    window = _service_window(extracted_flat.get("start_date"), extracted_flat.get("end_date"))
    hours_val = _hours_per_month_text(
        extracted_flat.get("authorized_minutes"),
        extracted_flat.get("start_date"),
        extracted_flat.get("end_date"),
    )
    end_mm = _iso_to_mmddyy(extracted_flat.get("end_date"))
    notes_text = (extracted_flat.get("notes") or "").strip()

    base_return: dict[str, Any] = {
        "ok": True,
        "spreadsheetId": cfg.spreadsheet_id,
        "worksheet": cfg.worksheet_name,
        "worksheetGid": cfg.worksheet_gid,
        "headerRow": header_row,
    }

    if match_row:
        batch: list[dict[str, Any]] = []

        ac = col.get("Authorization Comments")
        if ac:
            old = ws.cell(match_row, ac).value or ""
            old_s = str(old).rstrip()
            merged = (old_s + "\n" + auth_comments_block) if old_s else auth_comments_block
            batch.append({"range": rowcol_to_a1(match_row, ac), "values": [[merged]]})

        if window:
            ad_c = _first_empty_auth_date_col(ws, match_row, col)
            if ad_c:
                batch.append({"range": rowcol_to_a1(match_row, ad_c), "values": [[window]]})

        exp = col.get("Current Auth Expiration Date Format: MM/DD/YY")
        if exp and end_mm:
            batch.append({"range": rowcol_to_a1(match_row, exp), "values": [[end_mm]]})

        hp = col.get("Hours Per Month")
        if hp and hours_val:
            batch.append({"range": rowcol_to_a1(match_row, hp), "values": [[hours_val]]})

        sup = col.get("Areas of Support")
        if sup:
            av = areas or (extracted_flat.get("service_type") or "")
            if av:
                batch.append({"range": rowcol_to_a1(match_row, sup), "values": [[av]]})

        ast = col.get("Authorization Status")
        if ast:
            batch.append({"range": rowcol_to_a1(match_row, ast), "values": [["Received"]]})

        an = col.get("Additional Notes")
        if an and notes_text:
            oldn = ws.cell(match_row, an).value or ""
            olds = str(oldn).rstrip()
            nmerged = (olds + "\n\n" + notes_text) if olds else notes_text
            batch.append({"range": rowcol_to_a1(match_row, an), "values": [[nmerged]]})

        uci_c = col.get("UCI")
        if uci_c and sid and not str(ws.cell(match_row, uci_c).value or "").strip():
            batch.append({"range": rowcol_to_a1(match_row, uci_c), "values": [[sid]]})

        student_col_idx = col.get("Student")
        if student_col_idx and sname and not str(ws.cell(match_row, student_col_idx).value or "").strip():
            batch.append({"range": rowcol_to_a1(match_row, student_col_idx), "values": [[sname]]})

        scm = col.get("SC\n(First Name Last Name)")
        cm = extracted_flat.get("case_manager_name")
        if scm and cm:
            batch.append({"range": rowcol_to_a1(match_row, scm), "values": [[cm]]})

        if batch:
            ws.batch_update(batch, raw=False)

        return {**base_return, "mode": "masterfile_update", "updatedRow": match_row, "studentRowMatched": True}

    row_len = max(col.values()) if col else len(MASTERFILE_HEADERS)
    row = ["" for _ in range(row_len)]

    def set_cell(header: str, value: Any) -> None:
        if header not in col:
            return
        i = col[header] - 1
        if i < 0 or i >= len(row):
            return
        row[i] = "" if value is None else value

    set_cell("UCI", sid)
    set_cell("Student", sname)
    set_cell("Spanish", False)
    set_cell("Authorization Comments", auth_comments_block)
    set_cell("Contract Service Date 1st Auth", window)
    set_cell("Current Auth Expiration Date Format: MM/DD/YY", end_mm)
    set_cell("Hours Per Month", hours_val)
    set_cell("Authorization Status", "Received")
    set_cell("SC\n(First Name Last Name)", extracted_flat.get("case_manager_name"))
    set_cell("Areas of Support", areas or extracted_flat.get("service_type") or "")
    set_cell("Additional Notes", notes_text or "")

    ws.append_row(row, value_input_option="USER_ENTERED")
    return {
        **base_return,
        "mode": "masterfile_append",
        "studentRowMatched": False,
    }


def append_authorization_row(extracted_flat: dict[str, Any], meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Backwards-compatible name: now writes the masterfile-shaped row.
    """
    return append_masterfile_row(extracted_flat, meta=meta)
