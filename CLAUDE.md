# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

AI Case Study demo: a Job Fit & Salary Estimator. Upload a CV (PDF/DOCX), get back extracted attributes, a 5-dimensional seniority score (0–100), a deterministic salary estimate grounded in the [platy.cz](https://platy.cz) dataset (722 positions in [backend/data/salaries.jsonl](backend/data/salaries.jsonl)), and a concrete +30 % growth plan.

User-facing strings, log messages, and LLM prompts are written in **Czech** — preserve that language when editing them.

## Stack

- **Backend** ([backend/](backend/)): FastAPI + LangChain + OpenAI + ChromaDB + pydantic-settings, Python 3.12, managed by `uv`. Package name `cv_evaluator`, src layout under [backend/src/cv_evaluator/](backend/src/cv_evaluator/).
- **Frontend** ([frontend/app.py](frontend/app.py)): Streamlit. Single page – upload form, polls `GET /status/{job_id}` and `GET /logs/{job_id}` every 0.5 s, shows pipeline progress + live backend log console + final report (salary, seniority breakdown, profile, growth plan, matches table, explanation, cost footer). Reads `API_URL` from env (defaults to `http://backend:8000` for docker-compose).
- **Orchestration**: [docker-compose.yml](docker-compose.yml). Both services share `.env` at the repo root. Healthchecks use Python (`urllib.request`), no `curl` in slim image. Non-root user inside containers.
- **Streamlit config**: `frontend/.streamlit/config.toml` sets `maxUploadSize=10` (overrides default 200 MB).

## Run

```powershell
# Whole stack (preferred)
docker compose up -d --build
# Open http://localhost:8501

# Backend only (dev)
cd backend; uv sync; uv run uvicorn cv_evaluator.main:app --reload --host 0.0.0.0 --port 8000

# Frontend only (dev) – set API_URL to localhost since backend isn't reached via docker DNS
cd frontend; uv sync; $env:API_URL="http://localhost:8000"; uv run streamlit run app.py

# Tests
cd backend; make test          # 16 tests, ~0.1 s
cd backend; make eval          # 17 golden CVs + LLM-as-judge
cd backend; make eval-no-judge # without judge (cheaper)
```

`OPENAI_API_KEY` is required, read via `pydantic-settings` from `.env` at module import time. Backend crashes on startup if missing.

## Architecture

### Async job pipeline

`POST /api/v1/evaluate` accepts a PDF/DOCX upload (≤10 MB), creates a job, kicks off processing via `asyncio.create_task`, and returns `202` with a `job_id`. Client polls `GET /api/v1/status/{job_id}` (state) and `GET /api/v1/logs/{job_id}?since=N` (incremental log stream). See [routes.py](backend/src/cv_evaluator/api/routes.py).

Pipeline (each transition updates `JobStatus` in [job_store.py](backend/src/cv_evaluator/job_store.py)):

1. **PARSING** — [steps/parser.py](backend/src/cv_evaluator/steps/parser.py): PyMuPDF for PDF, python-docx for DOCX → `CVData(raw_text, filename)`.
2. **EXTRACTING** — [steps/extractor.py](backend/src/cv_evaluator/steps/extractor.py): LLM call #1 (gpt-4.1-nano, T=0). Returns `ExtractedCV` via `with_structured_output`. Skills are already classified into tiers (`expert/core/basic/unknown`) by the LLM in this single call – no separate normalizer step. Also extracts `personality_traits` (4 signal categories) and `career_trajectory` (ascending/stable/lateral/descending). Tenacity retry on transient OpenAI errors.
3. **SCORING** — [steps/scorer.py](backend/src/cv_evaluator/steps/scorer.py): deterministic 5D rule-based score 0–100. Maxima: experience=35, skills=25 (tier-weighted: expert=3.0, core=1.0, basic=0.3, unknown=0.5; saturates at 8 expert skills), education=10, role=15 (CZ + EN keywords with diacritics-stripped matching), personality=15.
4. **ESTIMATING** — [services/embeddings.py](backend/src/cv_evaluator/services/embeddings.py): `find_matching_positions` embeds query (built from `current_role + previous_roles + industries`, **not** skills) and returns top-k from Chroma. LRU cache on query embeddings.
5. **ANCHOR + GROWTH** — [steps/salary_anchor.py](backend/src/cv_evaluator/steps/salary_anchor.py) + [steps/growth_target.py](backend/src/cv_evaluator/steps/growth_target.py): deterministic salary anchor as weighted average of matches projected via seniority score + trajectory modifier (±3-8 %). Growth target uses the same Chroma vector search with k=25, filters for positions reaching `anchor.center × 1.30`, picks most similar.
6. **EXPLAINING** — [steps/finalizer.py](backend/src/cv_evaluator/steps/finalizer.py): LLM call #2 (gpt-4.1-mini, T=0.2). Receives profile + score + matches + anchor + growth_target as JSON, returns `FinalAnalysis(salary, explanation, growth_plan)`. Salary is **clamped to anchor ±10 %** defensively in case LLM ignores constraint.
7. **QUALITY ASSESSOR** — [steps/quality_assessor.py](backend/src/cv_evaluator/steps/quality_assessor.py): 5 sanity signals → `high/medium/low` confidence + warnings.
8. **DONE** — final `Report` (extracted + seniority + salary + anchor + explanation + growth_plan + matches + data_quality + cost) stored in `_jobs`.

`_jobs` is an **in-process dict** in [job_store.py](backend/src/cv_evaluator/job_store.py) — jobs do not survive restart and the backend cannot be horizontally scaled as-is. `update_job` overwrites `result`/`error` on every transition (only set to non-None on terminal states).

### Structured LLM extraction

Both LLM calls use `ChatOpenAI(...).with_structured_output(Model)` (OpenAI Structured Outputs / strict `json_schema`). **Do not switch back to `PydanticOutputParser`** – gpt-4.1-nano sometimes returns the schema itself, structured-output API does not.

`models.py` is the contract for LLM output, scorer input, and API response — changes ripple through prompts and the frontend. `Field(description=...)` strings are also LLM instructions (visible in JSON schema).

### Skill tier classification

There is **no hardcoded taxonomy file**. The extractor LLM classifies each skill's tier (`expert`/`core`/`basic`/`unknown`) and assigns canonical name in the same call. Definitions in [prompts/extractor.py](backend/src/cv_evaluator/prompts/extractor.py) with cross-domain examples (IT, healthcare, finance, construction, hospitality, …). Earlier iteration used `data/skill_taxonomy.json` with ~250 skills – removed because it didn't scale to long-tail professions (pizzař, kominík, sommelier).

### Salary retrieval (ChromaDB)

Two-stage to avoid re-embedding on every startup:

1. **Build (offline, once)**: `uv run python scripts/build_embeddings.py` reads `salaries.jsonl`, embeds via `text-embedding-3-small` (`position + group + duties`), writes vectors to `backend/data/positions_embeddings.jsonl`. Refuses to overwrite – delete file to regenerate.
2. **Load (every startup)**: [services/embeddings.py](backend/src/cv_evaluator/services/embeddings.py) opens persistent Chroma at `backend/data/chroma/`. If empty, hydrates from JSONL (no OpenAI calls). If populated, reuses. Wired via FastAPI `lifespan` in [main.py](backend/src/cv_evaluator/main.py).

Both `data/chroma/` and `data/positions_embeddings.jsonl` live under bind-mounted `backend/data/`, surviving container rebuilds. Delete `data/chroma/` alone to re-load from JSONL; delete JSONL to force full rebuild.

Query side (`find_matching_positions`) still calls OpenAI to embed the query (per-request, cached via LRU).

### Per-job log streaming to frontend

`log_store.py` defines `current_job_id: ContextVar` and a `JobLogHandler` registered on the `cv_evaluator` logger. `process_cv` calls `current_job_id.set(job_id)` at the start. The handler reads the ContextVar and routes log records into a per-job ring buffer (max 500 entries). Frontend polls `GET /logs/{job_id}?since=N`.

ContextVars are task-local in asyncio – concurrent jobs don't mix, even with shared logger. This is why pipeline functions (`compute_anchor`, `assess_quality`, `_score_skills`, …) don't take `job_id` parameters but their `logger.info(...)` still ends up in the right buffer.

### Cost tracking

`services/cost_tracker.py` exposes `cost_tracker` (singleton) and `CostCallback` (LangChain callback handler). The callback hooks `on_llm_end` to capture token usage and feed it to the tracker. Recorded as `CostEvent(job_id, model, input_tokens, output_tokens, cost_usd)`. `cost_tracker.summary(job_id)` returns `CostSummary` for inclusion in the final Report.

## Tests + Eval

- 16 unit tests in [backend/tests/](backend/tests/) — scorer (7), salary anchor (5), quality assessor (4). LLM-dependent paths covered by eval framework, not unit-tested.
- 17 golden CVs in [evals/datasets/golden_cvs.jsonl](backend/src/cv_evaluator/evals/datasets/golden_cvs.jsonl), covering IT (backend, frontend, devops, data, ML) + non-IT (vrchní sestra JIP, stavbyvedoucí, senior účetní, šéfkuchař, řidič kamionu) + edge cases (career changer, principal architect).
- LLM-as-judge in [evals/llm_judge.py](backend/src/cv_evaluator/evals/llm_judge.py) scores explanation/growth_plan on specificity / actionability / factual_grounding / consistency (1–5).
