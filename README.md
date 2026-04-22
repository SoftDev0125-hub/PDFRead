# Authorization Document Reader

Monorepo with a **frontend** (React) and **backend** (FastAPI) for ingesting authorization PDFs, extracting structured fields, and exporting result files.

## Structure

- `frontend/`: UI to upload PDFs, view extracted data, download results
- `backend/`: API + extraction pipeline (PDF text → extraction → JSON result)

## Run locally

### Backend

```bash
cd "backend"
python -m venv .venv
# Windows:
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8011
```

### Frontend

```bash
cd "frontend"
npm install
npm run dev
```

Open the UI at `http://localhost:5173`.

## Option A: LLM + Google Sheets setup

### OpenAI

- Set `OPENAI_API_KEY` in `backend/.env`
- Optional: set `OPENAI_MODEL` (default `gpt-4.1-mini`)

### Google Sheets (easiest: Service Account)

- Create a Google **Service Account** and download its JSON key.
- In [Google Cloud Console](https://console.cloud.google.com/) for that key’s project, enable **Google Sheets API** (and **Google Drive API** if you hit odd errors).
- Open the target spreadsheet in Google Sheets, click **Share**, and add the **service account email** (the `client_email` in the JSON) with role **Editor**. **Viewer is not enough**—writes will fail with `403` if the account cannot edit cells. “Anyone with the link” view access does **not** grant the service account edit rights; you must invite that email explicitly.
- Set:
  - `GOOGLE_SERVICE_ACCOUNT_JSON` (file path or inline JSON)
  - `GOOGLE_SHEETS_SPREADSHEET_ID`
  - `GOOGLE_SHEETS_WORKSHEET` (tab name), or optional `GOOGLE_SHEETS_WORKSHEET_ID` (the `gid` from the sheet URL)

When configured, each `POST /api/extract/{fileId}` syncs rows to the sheet (updates an existing student row when UCI/Student matches, otherwise appends).

**Check access:** from the repo root, run `python backend/scripts/check_google_sheets_access.py` (use the same Python/venv as the backend). Exit code `0` means a test row was written successfully; `2` means read works but write is blocked (almost always sharing role).

### OCR (for scanned PDFs)

If you want OCR to work, install Tesseract and set `TESSERACT_CMD` if needed.

