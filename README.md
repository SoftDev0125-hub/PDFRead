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
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd "frontend"
npm install
npm run dev
```

Open the UI at `http://localhost:5173`.

