# Drama Shorts Copilot (Shorten)

AWS 없이 **로컬 PC 또는 Docker 한 벌**로 돌리는 쇼츠 편집 보조 MVP입니다.  
비용 나가는 클라우드 스토리지/관리형 DB는 쓰지 않아도 됩니다.

## 구성

| 부분 | 역할 |
|------|------|
| `backend/` | FastAPI, Postgres(또는 스모크 시 SQLite), Redis, Celery worker |
| `frontend/` | Next.js 운영 UI |
| `docker-compose.yml` | Postgres + Redis + API + worker (로컬 전용) |

업로드·분석·후보·스크립트·비디오 초안·export(mock)까지 이어지는 흐름이 있습니다.

## 1) 가장 빠른 검증 (DB 없이)

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
python scripts/smoke_test.py
```

## 2) Docker로 API + DB + Redis (AWS 불필요)

리포지토리 루트에서:

```bash
cp backend/.env.example backend/.env
# 필요 시 backend/.env 에 OPENAI_API_KEY 만 추가 (없으면 mock LLM)
docker compose up --build
```

- API: `http://localhost:8000` — OpenAPI: `http://localhost:8000/docs`
- DB·파일은 **로컬 볼륨/폴더**에만 쌓입니다 (`postgres_data`, `backend/storage`).

**문제: `relation "video_drafts" already exists`로 `backend-api`가 바로 종료** — 예전에 DB에 테이블만 생기고 Alembic은 `0001`에 머문 상태였을 수 있습니다. 최신 코드는 이 경우에도 마이그레이션을 통과시킵니다. `docker compose up --build`로 다시 실행해 보세요. DB를 통째로 비우려면 `docker compose down -v` 후 다시 `up`(Postgres 데이터 삭제).

## 3) 프론트 (Next.js)

다른 터미널에서:

```bash
cd frontend
cp .env.example .env.local
# 기본값: NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1
npm install
npm run dev
```

브라우저: `http://localhost:3000`  
백엔드는 `CORS_ALLOWED_ORIGINS`에 `localhost:3000`이 잡혀 있어야 버튼·폼에서 API 호출이 됩니다(`backend/.env.example`·`docker-compose.yml` 기본 포함).

## 4) 집 서버 / 싼 VPS 한 대만 쓸 때

원리는 동일합니다.

- 같은 `docker compose`를 그 서버에서 실행
- 방화벽에서 API 포트(예: 8000)만 열거나, nginx로 리버스 프록시
- 프론트를 그 서버에서 `npm run build && npm start`로 돌리면 `NEXT_PUBLIC_API_BASE_URL`을 **공개 URL**로 바꿉니다

여전히 **S3·RDS 없이** 디스크 + 컨테이너 Postgres로 충분합니다.

## 문서

- API·환경 변수 상세: `backend/README.md`
- 거대 설계 메모: `plan.md`
