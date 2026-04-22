# Submission for reviewers

**Repository:** [github.com/SoftDev0125-hub/Authorization-Document-Reader](https://github.com/SoftDev0125-hub/Authorization-Document-Reader) (private is fine—invite the reviewer under **Settings → Collaborators** with at least **Read** access, or **Write** if they should push branches.)

**How to run:** see the project [README.md](../README.md) (backend on port `8011`, frontend on `5173`, copy `backend/.env.example` → `backend/.env`).

**Loom (~5 min):** use the outline at the end of this file. Show a real PDF upload → extraction → JSON + (if configured) Sheets result; pick **one** tricky decision and think out loud—no script rehearsal needed.

---

## One-page write-up

*Paste the section below into Google Docs or Word; use 11pt, normal margins, single spacing—it should fit about one printed page.*

---

### Authorization Document Reader — summary

**What I built**  
A small full-stack tool for operations staff: upload an authorization **PDF**, run an extraction pipeline, and get **structured fields** (student, UCI, dates, authorization number, service type, hours, case manager, notes, etc.) with **evidence snippets** and **warnings**. A **React** dashboard lists files, runs extraction, toggles evidence, and surfaces Google Sheets sync status. A **FastAPI** backend reads each PDF page with **PyMuPDF** (native text) or **Tesseract OCR** when text is too thin, then fills a schema either via **OpenAI** (JSON mode, temperature 0, **two-pass** completion for missing fields) or **regex heuristics** if the API is missing or fails. Results persist as **JSON** on disk and can **sync to a Google Sheet** aligned to a “masterfile”: **find the student row by UCI or name**, append to **Authorization Comments**, fill the next **Contract Service Date** slot, refresh expiration and hours, set **Authorization Status** to **Received** when a POS-style PDF is processed—otherwise **append** a new row. A small script verifies Sheets read vs write (common **403** when the service account is only a **Viewer**).

**Tradeoffs (2–3)**  
1. **LLM vs heuristics:** The LLM handles messy layouts and implicit labels; heuristics keep the app usable offline and when the API errors, but they only match patterns we encoded—worse on novel forms. I chose **LLM primary + heuristic fallback** instead of shipping rules-only or paying for extraction on every page without a gate.  
2. **Append-only vs in-place masterfile updates:** Appending rows is simpler and safer for automation; real SOPs expect **editing the student’s existing row**. I implemented **match-then-update** when UCI/Student hits, with **append** when no match—accepting duplicate risk if names don’t align with the sheet.  
3. **Evidence vs speed:** Returning per-field snippets and page indices helps trust and QA but enlarges payloads and UI noise; the UI defaults evidence on with a toggle rather than hiding everything behind a debug mode.

**Another ~10 hours**  
Add a **labeled PDF set** and a script to compute field-level precision/recall; **API authentication** and optional multi-tenant storage; **batch upload** and queue; **fuzzy header** matching for Sheets columns whose titles drift; **OAuth** (user-owned sheet) as an alternative to distributing service-account keys; **pytest** for the regex layer and sheet row-matcher.

**Edge cases in data / ops**  
Scanned pages route through **OCR** (quality varies); **hours** sometimes appear only as “HRS” with ambiguous monthly vs total semantics (we warn); **district** / **subject areas** were often missing on sample auths; **date** strings can be ambiguous across locales; Sheets **403** if the robot account isn’t an **Editor**; masterfile **header row** must expose **UCI** for our header discovery.

---

## Loom walkthrough (~5 minutes) — outline

1. **0:00–0:30** — Open repo README: what the stack is; show `backend/.env` exists but **do not** scroll API keys on screen.  
2. **0:30–1:30** — Terminal: `uvicorn` + `npm run dev`; open UI.  
3. **1:30–3:30** — Upload a **real** authorization PDF → **Run extraction** → scroll fields, **evidence** toggle, **warnings / validations**, **page routing** (text vs OCR). Download **JSON** if useful.  
4. **3:30–4:30** — If Sheets is configured: show success banner or **403 troubleshooting** block; optionally run `python backend/scripts/check_google_sheets_access.py` and interpret exit code.  
5. **4:30–5:00** — **One tricky decision (pick one, think out loud):** e.g. why **two-pass LLM** vs one shot; why **update row by UCI/name** vs always append; why **OCR threshold** vs always OCR; why **temperature 0** and JSON mode vs creative sampling.

**Tone:** narrate mistakes or uncertainty (“I’d validate this field against the PDF every time”)—reviewers care about judgment, not a polished marketing demo.
