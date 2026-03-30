# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Shorten** is a local-first Drama/Video Shorts Editing Assistant. It ingests long-form drama episodes and automatically generates short-form vertical video (9:16) candidates using a multi-signal analysis pipeline. The project is Korean-language and designed for single-machine deployment with no external cloud dependencies.

## Commands

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

make lint          # Ruff linter on app/, scripts/, alembic/
make format        # Ruff formatter
make smoke         # E2E smoke test (requires FFmpeg)

alembic upgrade head   # Apply DB migrations
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload  # Dev server
```

### Frontend

```bash
cd frontend
npm install
npm run dev        # Dev server on http://localhost:3000
npm run build
npm run lint       # ESLint (fails on warnings)
npm run lint:fix
```

### Docker (full stack)

```bash
docker compose up --build   # Postgres + Redis + API + Worker
docker compose down -v      # Stop and wipe volumes
```

## Architecture

### Stack
- **Backend**: FastAPI + SQLAlchemy 2.0 + Celery (Redis broker) + Alembic
- **Frontend**: Next.js 16 (App Router) + React 19 + TanStack Query
- **Storage**: Local disk for all video/audio/render files; PostgreSQL (or SQLite for local dev)

### Data Flow

**Episode Analysis Pipeline** (Celery task chain):
```
ingest_episode → transcode_proxy → detect_shots → extract_keyframes
  → extract_transcript → compute_signals → generate_candidates
```

**Content Generation Flow**:
```
Candidate → ScriptDraft (OpenAI/mock) → VideoDraft → short clip render → Export
```

### Key Design Decisions

- **No cloud**: `STORAGE_ROOT` is a local path; no S3 or managed DB
- **Mock LLM fallback**: Set `ALLOW_MOCK_LLM_FALLBACK=true` when `OPENAI_API_KEY` is absent
- **SQLite fallback**: `DATABASE_URL` defaults to SQLite for quick local testing
- **Celery eager mode**: `CELERY_TASK_ALWAYS_EAGER=true` runs tasks synchronously (used in smoke tests)
- **Composite candidates**: Candidates can span non-contiguous segments (`candidate_spans.py`, `composite_candidate_generation.py`)

### Backend Module Map (`backend/app/`)

| Path | Role |
|------|------|
| `api/v1/` | REST routes: episodes, candidates, script_drafts, video_drafts, exports, jobs |
| `core/config.py` | Pydantic Settings; all env vars loaded here |
| `core/celery_app.py` | Celery instance configuration |
| `db/models.py` | ORM models: Episode, Job, Shot, TranscriptSegment, Candidate, ScriptDraft, VideoDraft, Export |
| `tasks/pipelines.py` | All Celery task definitions and pipeline chains |
| `services/analysis_service.py` | Orchestrates the ingest→candidate pipeline |
| `services/candidate_generation.py` | Core multi-signal scoring (`ScoredWindow`, `WindowSeed`) |
| `services/candidate_events.py` | Drama pattern detection (question/payoff/reaction) |
| `services/candidate_rerank.py` | Optional LLM-based re-ranking |
| `services/vision_candidate_refinement.py` | Multimodal (frame + subtitle) scoring via vision model |
| `services/short_clip_service.py` | FFmpeg 9:16 vertical video render with subtitle burn-in |
| `services/storage_service.py` | All file path management for episode storage layout |
| `services/jobs.py` | Job state machine: QUEUED → RUNNING → SUCCEEDED/FAILED |

### Frontend Module Map (`frontend/`)

| Path | Role |
|------|------|
| `app/` | Next.js App Router pages (episodes, candidates, drafts, exports) |
| `components/` | React components; `jobs-live.tsx` and `candidate-jobs-and-drafts-live.tsx` use polling |
| `lib/api.ts` | All API fetch calls; base URL from `NEXT_PUBLIC_API_BASE_URL` |
| `lib/types.ts` | TypeScript interfaces mirroring backend DB models |
| `lib/public-api.ts` | Mutation helpers and polling utilities |

## Environment Variables

Copy `backend/.env.example` to `backend/.env`. Key variables:

| Variable | Default | Notes |
|----------|---------|-------|
| `DATABASE_URL` | SQLite path | Switch to Postgres for production |
| `REDIS_URL` | `redis://localhost:6380/0` | Also `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` |
| `OPENAI_API_KEY` | — | Required for real LLM; omit to use mock |
| `OPENAI_MODEL` | `gpt-4.1-mini` | |
| `VISION_CANDIDATE_RERANK` | `false` | Enable GPT-4 vision re-ranking |
| `STORAGE_ROOT` | `./storage` | Local path for all media files |
| `CELERY_TASK_ALWAYS_EAGER` | `false` | Set `true` in tests for synchronous execution |

Frontend: copy `frontend/.env.example` to `frontend/.env.local`; set `NEXT_PUBLIC_API_BASE_URL`.

## Testing

The smoke test at `backend/scripts/smoke_test.py` is the primary integration test. It:
- Generates a synthetic video with FFmpeg
- Runs the full analysis pipeline with `CELERY_TASK_ALWAYS_EAGER=true` and SQLite
- Validates candidate generation without requiring OpenAI or Redis

Run with `make smoke` from `backend/`.

## Database Migrations

Migration history in `backend/alembic/versions/`:
1. Initial schema (Episode, Job, Shot, TranscriptSegment, Candidate, ScriptDraft)
2. video_drafts_exports
3. candidate_short_clip
4. video_draft_metadata

Always run `alembic upgrade head` after pulling changes that include new migrations.
