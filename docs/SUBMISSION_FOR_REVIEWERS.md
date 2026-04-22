## Submission notes (reviewer quickstart)

This repo contains a lab report biomarker extraction web app.

### Run locally

- Backend: `backend/` (FastAPI)
- Frontend: `frontend/` (Next.js)

### What to look at

- **Backend extraction**: `backend/app/routers/extraction.py`
- **Visible-text-only PDF extraction**: `backend/app/services/page_pipeline.py`
- **Compact LLM pipeline**: `backend/app/services/lab_openai_extract.py`
- **Optional background jobs**: `backend/app/routers/jobs.py`, `backend/app/services/jobs.py`

