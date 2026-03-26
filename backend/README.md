# Shorts Backend

FastAPI + Celery + SQLAlchemy backend for the shorts MVP flow.

**비용·AWS 없이** 쓰는 기준: DB/Redis는 Docker(또는 로컬), 파일은 `STORAGE_ROOT` 디스크만 사용합니다. 전체 UI까지 한 번에 쓰는 방법은 리포지토리 루트 `README.md`를 보세요.

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
pip install -e ".[dev]"
python scripts/smoke_test.py
```

이 검증은 아래 흐름을 확인합니다.

- upload
- analyze
- candidate listing
- script draft generation
- video draft 생성 → mock rerender → approve → export → `GET /exports/{id}`

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

## Lint / Format

로컬 가상환경 기준으로 아래 명령을 씁니다.

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
make lint
make format
```

직접 실행하려면:

```bash
./.venv/bin/ruff check app scripts alembic
./.venv/bin/ruff format app scripts alembic
```

## API Flow

1. `POST /api/v1/episodes`
1b. `GET /api/v1/episodes/{episode_id}/source-video` — 원본 영상 스트리밍(로컬 UI 재생)
2. `POST /api/v1/episodes/{episode_id}/analyze`
3. `GET /api/v1/jobs?episode_id=...`
4. `GET /api/v1/episodes/{episode_id}/candidates`
5. `GET /api/v1/candidates/{candidate_id}`
6. `POST /api/v1/candidates/{candidate_id}/script-drafts`
7. `GET /api/v1/candidates/{candidate_id}/script-drafts`
8. `PATCH /api/v1/script-drafts/{script_draft_id}`
9. `POST /api/v1/script-drafts/{script_draft_id}/select`
10. `POST /api/v1/candidates/{candidate_id}/video-drafts` — 비디오 초안(mock)
11. `GET /api/v1/candidates/{candidate_id}/video-drafts`
12. `GET|PATCH /api/v1/video-drafts/{video_draft_id}`
13. `POST /api/v1/video-drafts/{video_draft_id}/rerender` — mock 재렌더(Celery 미연동 시 즉시 완료 job)
14. `POST /api/v1/video-drafts/{video_draft_id}/approve` / `.../reject`
15. `POST /api/v1/video-drafts/{video_draft_id}/exports` — mock export
16. `GET /api/v1/exports/{export_id}`
17. `POST /api/v1/candidates/{candidate_id}/short-clip` — FFmpeg로 구간 자르기·9:16·자막 번인 (worker 필요)
18. `GET /api/v1/candidates/{candidate_id}/short-clip/video` — 렌더된 쇼츠 mp4 스트리밍

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
- `CORS_ALLOWED_ORIGINS` — Next.js(`localhost:3000`) 등에서 브라우저가 API를 직접 호출할 때 필요

OpenAI 키가 없으면 deterministic mock script draft가 생성됩니다.

## Notes

- mock analysis는 proxy/audio/shots/transcripts/candidates를 합성 생성합니다.
- 비디오 초안·rerender·export는 **placeholder 파일 + DB 레코드** 수준의 mock입니다. 실제 FFmpeg/TTS/Celery 태스크는 별도 구현이 필요합니다.
- 파일 저장은 **항상 로컬 디스크(`STORAGE_ROOT`)** 기준입니다. 혼자 쓰는 PC·집 서버·저렴한 VPS 한 대면 충분합니다.
- 프론트는 별도 `frontend/` Next.js 앱으로 연결됩니다.
