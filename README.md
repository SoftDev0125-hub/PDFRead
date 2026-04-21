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
- Share the target Google Sheet with the **service account email**.
- Set:
  - `GOOGLE_SERVICE_ACCOUNT_JSON` (file path or inline JSON)
  - `GOOGLE_SHEETS_SPREADSHEET_ID`
  - `GOOGLE_SHEETS_WORKSHEET` (tab name)

When configured, each `POST /api/extract/{fileId}` will append a row to the sheet.

### OCR (for scanned PDFs)

If you want OCR to work, install Tesseract and set `TESSERACT_CMD` if needed.

