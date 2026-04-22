"""
Verify the service account can read and write the spreadsheet from .env.

Run (from anywhere):

  python backend/scripts/check_google_sheets_access.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def main() -> int:
    os.chdir(BACKEND)
    sys.path.insert(0, str(BACKEND))

    from dotenv import load_dotenv

    load_dotenv(BACKEND / ".env")

    from app.services.sheets_writer import (
        _config,
        _load_service_account,
        troubleshooting_for_sheets_permission_denied,
    )

    import gspread

    sa = _load_service_account()
    email = sa.get("client_email")
    print("Service account (share the sheet with this address as Editor):")
    print(f"  {email}\n")

    cfg = _config()
    print("Spreadsheet ID:", cfg.spreadsheet_id)
    print("Worksheet gid:", cfg.worksheet_gid, "| name fallback:", cfg.worksheet_name)

    gc = gspread.service_account_from_dict(sa)
    try:
        sh = gc.open_by_key(cfg.spreadsheet_id)
        print("\nopen_by_key: OK —", repr(sh.title))
    except Exception as e:
        print("\nopen_by_key: FAILED —", type(e).__name__, e)
        return 1

    try:
        if cfg.worksheet_gid is not None:
            ws = sh.get_worksheet_by_id(cfg.worksheet_gid)
        else:
            ws = sh.worksheet(cfg.worksheet_name)
        print("worksheet:", repr(ws.title), "gid=", ws.id)
    except Exception as e:
        print("\nworksheet: FAILED —", type(e).__name__, e)
        return 1

    try:
        ws.append_row(["_auth_reader_access_check_delete_this_row"], value_input_option="USER_ENTERED")
        print("\nwrite test (append_row): OK — delete the test row in the sheet if you like.")
        return 0
    except Exception as e:
        print("\nwrite test (append_row): FAILED —", type(e).__name__, e)
        tw = troubleshooting_for_sheets_permission_denied()
        print("\n--- Fix (403 / permission denied) ---")
        for line in tw.get("steps", []):
            print(line)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
