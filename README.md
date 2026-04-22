# Lab Report Biomarker Extractor

**Repository:** [github.com/SoftDev0125-hub/PDFRead](https://github.com/SoftDev0125-hub/PDFRead)

Monorepo with a **frontend** (React) and **backend** (FastAPI) for uploading lab-report PDFs/images, extracting **all biomarkers**, standardizing names/units into English, and classifying each result as **optimal**, **normal**, or **out of range** using the report’s age/sex-specific reference ranges.

**Reviewer materials:** one-page write-up + Loom outline → [docs/SUBMISSION_FOR_REVIEWERS.md](docs/SUBMISSION_FOR_REVIEWERS.md). For a private repo, add the reviewer under GitHub **Settings → Collaborators** (Read is enough to review code).

## Prerequisites

- **Python** 3.11+ recommended (3.10+ should work)
- **Node.js** 18+ and npm
- Optional: **OpenAI API key** for LLM extraction

## Structure

- `frontend/`: UI to upload PDFs, view extracted data, download results
- `backend/`: API + extraction pipeline (PDF text → extraction → JSON result)

## Run locally

1. Clone the repo and copy the environment template into `backend/.env`:

```bash
# macOS / Linux:
cp backend/.env.example backend/.env

# Windows (cmd), from repo root:
copy backend\.env.example backend\.env
```

Edit `backend/.env` — set `OPENAI_API_KEY` if you want LLM extraction.

2. Start backend and frontend in two terminals (see below).

### Backend

```bash
cd "backend"
python -m venv .venv
# Windows:
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8012
```

### Frontend

```bash
cd "frontend"
npm install
npm run dev
```

Open the UI at `http://localhost:3000`.

## Suggested cloud resources (no deployment required)

- **Frontend**: static hosting on S3 + CloudFront (or Vercel/Netlify).
- **Backend API**: containerized FastAPI on ECS Fargate (or Cloud Run on GCP).
- **Storage**: object storage (S3 / GCS) for uploaded PDFs and extracted JSON.
- **Async extraction** (recommended for large PDFs/OCR): queue + workers (SQS + ECS workers, or Pub/Sub + Cloud Run jobs).
- **Secrets**: managed secrets store (AWS Secrets Manager / GCP Secret Manager) for `OPENAI_API_KEY`.
- **Observability**: centralized logs + traces (CloudWatch + X-Ray, or GCP Logging + Trace).

## OpenAI setup

### OpenAI

- Set `OPENAI_API_KEY` in `backend/.env`
- Optional: set `OPENAI_MODEL` (default `gpt-4.1-mini`)

### Notes

- This app extracts **visible PDF text only** (OCR is disabled by design).

