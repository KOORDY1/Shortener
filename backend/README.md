# Shorts Backend

FastAPI + Celery + SQLAlchemy backend for the shorts MVP flow.

## 포함 범위

- `episodes`, `jobs`, `candidates`, `script_drafts` 중심 P0/P1 API
- mock analysis pipeline
- OpenAI 기반 script/title 생성 + mock fallback
- Alembic 초기 마이그레이션
- Postgres + Redis + Celery worker 실행 경로

## 빠른 로컬 검증

SQLite + eager Celery 기반으로 가장 빠르게 흐름을 확인하는 방법입니다.

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e .
python scripts/smoke_test.py
```

이 검증은 아래 흐름을 확인합니다.

- upload
- analyze
- candidate listing
- script draft generation

## 실환경 유사 실행

루트에서 아래 순서로 실행합니다.

```bash
cp backend/.env.example backend/.env
docker compose up --build
```

구성:

- `postgres`: 운영 DB
- `redis`: Celery broker/result backend
- `backend-api`: FastAPI API 서버
- `backend-worker`: Celery worker

API 서버가 뜨면 시작 시 `alembic upgrade head`가 자동으로 실행됩니다.

## API Flow

1. `POST /api/v1/episodes`
2. `POST /api/v1/episodes/{episode_id}/analyze`
3. `GET /api/v1/jobs?episode_id=...`
4. `GET /api/v1/episodes/{episode_id}/candidates`
5. `GET /api/v1/candidates/{candidate_id}`
6. `POST /api/v1/candidates/{candidate_id}/script-drafts`
7. `GET /api/v1/candidates/{candidate_id}/script-drafts`
8. `PATCH /api/v1/script-drafts/{script_draft_id}`
9. `POST /api/v1/script-drafts/{script_draft_id}/select`

## 환경 변수

`.env.example` 기본값은 Postgres + Redis + worker 구성을 기준으로 잡혀 있습니다.

- `DATABASE_URL`
- `REDIS_URL`
- `CELERY_BROKER_URL`
- `CELERY_RESULT_BACKEND`
- `CELERY_TASK_ALWAYS_EAGER`
- `OPENAI_API_KEY`
- `OPENAI_MODEL`
- `ALLOW_MOCK_LLM_FALLBACK`
- `STORAGE_ROOT`

OpenAI 키가 없으면 deterministic mock script draft가 생성됩니다.

## Notes

- mock analysis는 proxy/audio/shots/transcripts/candidates를 합성 생성합니다.
- 렌더/TTS/export는 후속 단계로 남겨 두었습니다.
- 프론트는 별도 `frontend/` Next.js 앱으로 연결됩니다.
