from __future__ import annotations

import json
import os
from dataclasses import dataclass
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


def append_authorization_row(extracted_flat: dict[str, Any]) -> dict[str, Any]:
    """
    Appends a row in the Option A required order:
    student name, student ID, district, service type, authorized minutes,
    start date, end date, authorization number, case manager name, subject areas, notes
    """
    cfg = _config()
    client = _client()
    sh = client.open_by_key(cfg.spreadsheet_id)
    ws = sh.worksheet(cfg.worksheet_name)

    subject_areas = extracted_flat.get("subject_areas")
    if isinstance(subject_areas, list):
        subject_areas = ", ".join([str(x) for x in subject_areas if x is not None])

    row = [
        extracted_flat.get("student_name"),
        extracted_flat.get("student_id"),
        extracted_flat.get("district"),
        extracted_flat.get("service_type"),
        extracted_flat.get("authorized_minutes"),
        extracted_flat.get("start_date"),
        extracted_flat.get("end_date"),
        extracted_flat.get("authorization_number"),
        extracted_flat.get("case_manager_name"),
        subject_areas,
        extracted_flat.get("notes"),
    ]

    ws.append_row(row, value_input_option="USER_ENTERED")
    return {"ok": True, "spreadsheetId": cfg.spreadsheet_id, "worksheet": cfg.worksheet_name}

