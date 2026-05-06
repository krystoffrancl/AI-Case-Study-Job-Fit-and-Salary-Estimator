# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

AI Case Study demo: a Job Fit & Salary Estimator. Upload a CV (PDF/DOCX), get back extracted attributes, a seniority score, and a salary estimate grounded in a Czech salary dataset ([backend/data/salaries.jsonl](backend/data/salaries.jsonl)).

User-facing strings, log messages, and LLM prompts are written in **Czech** — preserve that language when editing them.

## Stack

- **Backend** ([backend/](backend/)): FastAPI + LangChain + OpenAI + ChromaDB, Python 3.12, managed by `uv`. Package name `cv_evaluator`, src layout under [backend/src/cv_evaluator/](backend/src/cv_evaluator/).
- **Frontend** ([frontend/app.py](frontend/app.py)): Streamlit. Single page – upload form, polls `GET /status/{job_id}` every 0.5s inside an `st.status` widget showing pipeline stage checklist, then renders the `Report` (animated salary count-up, progress bar for seniority, profile, top matches table, explanation). Reads `API_URL` from env (defaults to `http://backend:8000` for docker-compose; set to `http://localhost:8000` for local dev).
- **Orchestration**: [docker-compose.yml](docker-compose.yml). Both services share a single `.env` at the repo root (not `backend/.env`, despite the file existing there — `docker-compose` reads `./.env`).

`backend/.python-version` pins 3.14 but `pyproject.toml` requires `>=3.12` and the Dockerfile uses `python:3.12-slim`. Use 3.12 locally to match production.

## Run

```powershell
# Whole stack
docker-compose up --build

# Backend only (dev)
cd backend; uv sync; uv run uvicorn cv_evaluator.main:app --reload --host 0.0.0.0 --port 8000

# Frontend only (dev) – set API_URL to localhost since backend isn't reached via docker DNS
cd frontend; uv sync; $env:API_URL="http://localhost:8000"; uv run streamlit run app.py
```

`OPENAI_API_KEY` is required and is read at import time in [backend/src/cv_evaluator/config.py](backend/src/cv_evaluator/config.py) — the backend will crash on startup if it is missing.

There is no test suite or linter configured yet.

## Architecture

### Async job pipeline

`POST /api/v1/evaluate` accepts a PDF/DOCX upload (≤10 MB), creates a job, kicks off processing via `asyncio.create_task`, and returns `202` with a `job_id`. The client polls `GET /api/v1/status/{job_id}`. See [routes.py](backend/src/cv_evaluator/api/routes.py).

Pipeline (each transition updates `JobStatus` in [job_store.py](backend/src/cv_evaluator/job_store.py)):

1. **PARSING** — [steps/parser.py](backend/src/cv_evaluator/steps/parser.py): PyMuPDF for PDF, python-docx for DOCX → `CVData(raw_text, filename)`.
2. **EXTRACTING** — [steps/extractor.py](backend/src/cv_evaluator/steps/extractor.py): LLM call #1, structured `ExtractedCV` via `PydanticOutputParser`.
3. **SCORING** — [steps/scorer.py](backend/src/cv_evaluator/steps/scorer.py): rule-based 0–100 seniority across experience/skills/education/role keywords.
4. **ESTIMATING** — [services/embeddings.py](backend/src/cv_evaluator/services/embeddings.py): `find_matching_positions` embeds `roles + skills + industries` and returns top-k from Chroma.
5. **EXPLAINING** — [steps/finalizer.py](backend/src/cv_evaluator/steps/finalizer.py): LLM call #2 returns combined `FinalAnalysis(salary, explanation)` from profile + score + matches in **one** structured call.
6. **DONE** — final `Report` (extracted + seniority + salary + explanation + matches) stored in `_jobs`.

`_jobs` is an **in-process dict** — jobs do not survive a restart and the backend cannot be horizontally scaled as-is. `update_job` overwrites `result`/`error` on every transition (only set to non-None on terminal states), so don't rely on intermediate `result` values.

### Structured LLM extraction

Both LLM calls use `ChatOpenAI(...).with_structured_output(Model)`, which translates to OpenAI Structured Outputs (strict `json_schema` response format) — constrained decoding guarantees the output matches the Pydantic schema. **Do not switch back to `PydanticOutputParser`**: smaller models (gpt-4.1-nano in particular) sometimes return the schema itself instead of an instance and the parser fails. The structured-output API does not have that failure mode.

Extractor uses `gpt-4.1-nano` (temperature=0) against [`ExtractedCV`](backend/src/cv_evaluator/models.py); finalizer uses `gpt-4.1-mini` (temperature=0.2) against [`FinalAnalysis`](backend/src/cv_evaluator/models.py) — slightly higher temperature because salary refinement and explanation benefit from some creativity. Prompts in [prompts/](backend/src/cv_evaluator/prompts/) **must not** contain `{format_instructions}` — it's no longer injected. The Pydantic models in [models.py](backend/src/cv_evaluator/models.py) are the contract for both LLM output and API response — changes there ripple through prompts and the frontend.

### Salary retrieval (ChromaDB)

Two-stage design to avoid re-embedding on every startup:

1. **Build (offline, once)**: `uv run python scripts/build_embeddings.py` reads `salaries.jsonl`, calls `text-embedding-3-small` for each position (`position + group + duties`), and writes vectors to `backend/data/positions_embeddings.jsonl`. Refuses to overwrite — delete the file to regenerate.
2. **Load (every startup)**: [services/embeddings.py](backend/src/cv_evaluator/services/embeddings.py) opens the persistent Chroma collection at `backend/data/chroma/`. If empty, it pushes pre-computed vectors from the JSONL into the collection (no OpenAI calls). If populated, it just reuses it. Wired via FastAPI `lifespan` in [main.py](backend/src/cv_evaluator/main.py).

`positions_embeddings.jsonl` is the canonical artifact — once generated, every fresh container or clone hydrates Chroma from it without OpenAI cost. Both `data/chroma/` (runtime cache) and `data/positions_embeddings.jsonl` live under bind-mounted `backend/data/`, so they survive container rebuilds. Delete `backend/data/chroma/` alone to force a re-load from the JSONL; delete the JSONL to force a full rebuild.

Query side (`find_matching_positions`) still calls OpenAI to embed the query string built from `ExtractedCV` (roles + skills + industries) — that one is per-request and cannot be cached this way.
