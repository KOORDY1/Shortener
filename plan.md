좋다.
그럼 이 툴은 **“에피소드 1개를 넣으면, 사람이 검수 가능한 해설형 Shorts 초안을 여러 개 뽑아주는 내부 편집 보조 시스템”**으로 정의하겠다.

아래는 바로 개발 들어갈 수 있는 수준의 **MVP 기능명세서**다.

---

# 1. 제품 정의

## 제품명(가칭)

**Drama Shorts Copilot**

## 목표

드라마 1개 에피소드를 업로드하면 시스템이:

* 장면을 분석하고
* Shorts 후보 구간을 추출하고
* 각 후보에 맞는 해설형 스크립트를 만들고
* TTS + 자막 + 기본 편집이 들어간 **초안 영상**을 여러 개 생성한 뒤
* 운영자가 검수/수정 후 export 할 수 있게 한다.

## MVP의 핵심 가치

핵심은 **완전자동 업로드**가 아니라 다음 3가지다.

1. **쓸만한 장면 후보를 빨리 찾는다**
2. **해설형 Shorts 초안을 대량 생성한다**
3. **운영자가 고르는 시간과 편집 시간을 줄인다**

---

# 2. MVP 범위

## MVP에 포함

* 영상 업로드
* 자막 추출 또는 업로드
* 장면 분할
* 후보 Shorts 구간 자동 추출
* 해설 포맷 2~3종 자동 생성
* TTS 음성 입힌 세로형 초안 영상 생성
* 운영자 검수/수정 UI
* MP4 / SRT / 스크립트 export

## MVP에 제외

* 유튜브 자동 업로드
* 다계정 업로드 자동화
* 저작권 회피 기능
* 완전 무인 자동 배포
* 다중 사용자 협업 권한관리의 고도화
* 모바일 앱

---

# 3. 주요 사용자

## 1) 운영자

* 에피소드 업로드
* 후보 Shorts 검토
* 제목/스크립트 수정
* export 실행

## 2) 편집자

* 컷 순서 조정
* 자막 수정
* TTS 재생성
* 최종 초안 확정

MVP에서는 사실상 **운영자 1인 + 편집자 1인 역할 통합**으로 봐도 된다.

---

# 4. 전체 워크플로우

## Step 1. 에피소드 업로드

입력:

* 영상 파일(mp4, mkv, mov)
* 선택: 자막 파일(srt, vtt)
* 선택: 드라마명 / 시즌 / 에피소드명
* 선택: 타깃 채널

  * 한국인 대상 미국드라마
  * 미국인 대상 한국드라마

## Step 2. 전처리

시스템이 자동 수행:

* 영상 표준화
* 오디오 추출
* 해상도/길이/코덱 분석
* 프레임 썸네일 생성

## Step 3. 분석

* 장면 전환 탐지
* 대사 추출(ASR)
* 자막 정렬
* 감정/갈등/반전/웃음 포인트 탐지
* 독립적 Shorts 후보 구간 생성

## Step 4. 후보 Shorts 생성

후보마다:

* 훅 3개
* 제목 5개
* 20~35초 스크립트 2개
* 해설 포맷 2~3개
* 리스크 점수
* 예상 완시율 점수(내부 점수)

## Step 5. 초안 렌더링

후보를 선택하면 자동으로:

* 세로형 캔버스 생성(1080x1920)
* 컷 재배열
* 줌/정지화면/강조문구 적용
* TTS 입힘
* 자막 생성
* draft mp4 생성

## Step 6. 운영자 검수

운영자는:

* 컷 삭제/교체
* 스크립트 수정
* 자막 수정
* TTS 재생성
* 제목 선택
* export 확정

## Step 7. Export

출력:

* 최종 mp4
* srt
* 스크립트 txt/md
* 제목 후보 json/csv
* 편집 메타데이터 json

---

# 5. 기능 명세

## A. 업로드 / 인제스트 모듈

### 기능

* 에피소드 파일 업로드
* 업로드 진행률 표시
* 파일 유효성 검사
* 자막 파일 업로드 지원
* 파일별 메타데이터 저장

### 입력

* video_file
* subtitle_file(optional)
* show_title
* season_number(optional)
* episode_number(optional)
* target_channel
* source_language

### 출력

* episode_id
* 인제스트 상태
* 영상 메타정보
* 분석 대기열 등록

### 예외 처리

* 지원하지 않는 포맷
* 파일 손상
* 오디오 트랙 없음
* 자막 인코딩 오류

---

## B. 전처리 / 분석 모듈

### 기능

1. 영상 표준화

* 프록시 파일 생성
* 프레임레이트 정규화
* 오디오 분리

2. 장면 분할

* shot boundary detection
* 유사 샷 병합

3. 대사 추출

* 자막이 있으면 우선 사용
* 없으면 ASR 수행
* 타임코드 정렬

4. 화자/감정 단서 추출

* 화자 추정(optional)
* 음성 에너지
* 말속도
* 감정 점수
* 긴장감 상승 구간

5. 비주얼 태깅

* 얼굴 클로즈업 여부
* 인물 수
* 표정 변화
* 화면 전환 강도
* 텍스트 오버레이 여유 공간 추정

### 내부 산출물

* shots
* transcript_segments
* dialogue_blocks
* scene_clusters
* highlight_signals

---

## C. 후보 Shorts 추출 모듈

이 모듈이 사실상 핵심이다.

### 목표

에피소드에서 **독립적으로 소비 가능한 구간**을 자동 추출한다.

### 후보 생성 규칙

각 후보는 기본적으로:

* 총 길이: **18~35초**
* 원본 컷 수: **4~7개**
* 원본 각 컷 길이: **0.8~2.5초**
* 해설 중심 구조
* 초반 2초 안에 훅 가능해야 함

### 점수 기준

각 후보에 아래 점수를 매긴다.

* **Hook strength**: 첫 2초 내 흥미 유발 가능성
* **Standalone clarity**: 맥락 없이도 이해 가능한가
* **Conflict / tension**: 갈등, 긴장, 반전
* **Emotion**: 감정 밀도
* **Dialogue clarity**: 대사 전달 가능성
* **Visual clarity**: 세로 영상으로 잘 보이는가
* **Commentary potential**: 해설 포인트가 뚜렷한가
* **Source dependence penalty**: 원본 자체에 지나치게 의존하는가
* **Repetition penalty**: 기존 초안들과 구조가 지나치게 비슷한가

### 후보 유형

MVP에서는 3종만 넣는 게 맞다.

#### 1) 문화/맥락 해설형

예:

* 왜 여기서 분위기가 싸해졌는지
* 미국식 직장화법의 진짜 의미
* 한국인이 놓치기 쉬운 맥락

#### 2) 뉘앙스/번역 해설형

예:

* 자막은 맞는데 감정은 다르다
* 이 말은 번역보다 관계가 중요하다

#### 3) 심리/관계 분석형

예:

* 이 표정 하나로 관계가 끝난 장면
* 말보다 침묵이 더 무서운 이유

### 출력

후보 10~30개
각 후보마다:

* candidate_id
* start/end time
* score breakdown
* 추천 포맷
* 원본 샷 리스트
* 추천 훅/제목/스크립트

---

## D. 스크립트 생성 모듈

### 목표

원본 줄거리 낭독이 아니라 **해설형 스크립트**를 만든다.

### 입력

* 후보 장면
* 타깃 채널
* 포맷 유형
* 톤 설정
* 언어

### 출력

후보당:

* 훅 3개
* 제목 5개
* 본문 스크립트 2개
* CTA 2개

### 스크립트 구조

기본 구조:

1. Hook
2. 장면 소개
3. 맥락/뉘앙스/심리 해설
4. 결론
5. 다음 영상 연결

### 길이 제한

* 음성 분량 기준 **18~30초**
* 문장 수 **4~7문장**
* 한 문장 너무 길지 않게

### 금지 규칙

* 단순 줄거리 요약만 하는 문안 금지
* 동일 템플릿 반복 금지
* 장면 설명보다 해설이 적은 경우 경고

---

## E. TTS / 자막 모듈

### 기능

* 채널별 기본 TTS 보이스 설정
* 스크립트 기반 음성 생성
* 문장 단위 타이밍 정렬
* 자동 자막 생성

### MVP 옵션

채널별 1개 음성만 우선 지원

* 한국어 채널용 1 voice
* 영어 채널용 1 voice

### 자막 규칙

* 2줄 이하
* 라인당 글자수 제한
* 핵심 단어 강조 가능
* 단순 대사 자막보다 해설 자막 우선

---

## F. 초안 영상 생성 모듈

### 출력 형식

* 1080x1920 mp4
* H.264
* 24~30fps
* burned-in captions 옵션

### 자동 편집 규칙

* 훅 텍스트 오버레이
* 컷 간 빠른 전환
* 중요 단어 강조
* freeze frame / zoom / crop
* 세로형 안전구역 적용

### MVP 편집 템플릿

#### Template A: 맥락 해설형

* hook title
* clip
* voiceover
* clip
* summary line

#### Template B: 번역/뉘앙스형

* subtitle mismatch intro
* clip
* explanation overlay
* closing line

#### Template C: 심리분석형

* key-expression freeze
* clip fragments
* analysis voiceover
* ending insight

---

## G. 검수 / 편집 UI

이 부분은 꼭 있어야 한다.
MVP라도 여기 없으면 실무에서 못 쓴다.

### 화면 1. 에피소드 상세

보여줄 것:

* 에피소드 정보
* 분석 상태
* timeline
* 장면 리스트
* transcript

### 화면 2. 후보 리스트

각 카드에:

* 썸네일
* 길이
* 총점
* 포맷 유형
* 추천 제목 1개
* 리스크 점수
* draft 생성 버튼

### 화면 3. 후보 상세

보여줄 것:

* 원본 구간 미리보기
* 샷 리스트
* 훅/제목/스크립트 후보
* 추천 해설 포인트
* risk breakdown

### 화면 4. draft editor

기능:

* 스크립트 직접 수정
* 컷 삭제/재정렬
* TTS 재생성
* 자막 문구 수정
* 강조 문구 수정
* 썸네일 프레임 선택
* export 버튼

### 화면 5. export 센터

보여줄 것:

* 렌더 상태
* 출력 파일 목록
* 다운로드 링크
* 히스토리

---

# 6. 리스크 스코어 기능

내부 툴이라도 이건 넣는 게 좋다.

### 목적

운영자가 **“이 초안은 너무 원본 의존도가 높다”**는 걸 한눈에 보게 한다.

### 점수 요소

* 원본 장면 총량 비율
* 연속 원본 장면 최장 길이
* 해설 음성 비율
* 해설 자막 비율
* 템플릿 반복도
* 이전 영상과 유사도
* 동일 에피소드 내 중복 장면 사용도

### 결과값

* Low
* Medium
* High

### 경고 예시

* “연속 원본 장면이 4.8초로 너무 깁니다”
* “해설 비중이 낮습니다”
* “기존 3개 draft와 구조가 지나치게 유사합니다”

---

# 7. 데이터 모델

## Episode

* id
* title
* season
* episode_number
* original_language
* target_channel
* file_path
* duration
* status
* created_at

## Shot

* id
* episode_id
* start_time
* end_time
* thumbnail_path
* face_count
* motion_score
* closeup_score

## TranscriptSegment

* id
* episode_id
* start_time
* end_time
* text
* speaker(optional)
* source_type(subtitle/asr)

## Candidate

* id
* episode_id
* type
* start_time
* end_time
* total_score
* hook_score
* clarity_score
* commentary_score
* risk_score
* status

## ScriptDraft

* id
* candidate_id
* language
* hook_text
* title_options
* script_text
* cta_text
* selected_version

## VideoDraft

* id
* candidate_id
* script_draft_id
* render_path
* subtitle_path
* template_type
* tts_voice
* status

## ReviewAction

* id
* video_draft_id
* reviewer
* action_type
* notes
* created_at

---

# 8. 권장 기술스택

네가 Python과 웹스택에 익숙하니까, MVP는 이 조합이 효율적이다.

## 백엔드

* **Python + FastAPI**
* 이유: 영상 처리 파이프라인, AI 연동, 비동기 job에 유리

## 작업 큐

* **Celery + Redis**
* 긴 렌더링/분석 job 분리

## DB

* **PostgreSQL**

## 스토리지

* 로컬 디스크 또는 **S3 호환 스토리지**
* episode 원본 / 프록시 / draft / 썸네일 / 자막 저장

## 프론트엔드

* **Next.js**
* 내부 운영툴 대시보드 제작에 적합

## 영상 처리

* **FFmpeg**
* 컷, 리사이즈, 오디오, 렌더 전부 핵심

## 장면 분할

* **PySceneDetect** 계열 또는 자체 ffmpeg 기반 shot detection

## 음성/자막

* ASR: Whisper 계열
* TTS: 운영용 1~2개 voice provider

## LLM

* 스크립트/제목/해설 포인트 생성

---

# 9. API 초안

## POST /episodes

에피소드 업로드

## GET /episodes/:id

에피소드 상태 조회

## POST /episodes/:id/analyze

분석 시작

## GET /episodes/:id/candidates

후보 리스트 조회

## GET /candidates/:id

후보 상세 조회

## POST /candidates/:id/generate-script

스크립트 후보 생성

## POST /candidates/:id/render-draft

초안 렌더링

## PATCH /drafts/:id

스크립트/자막/템플릿 수정

## POST /drafts/:id/export

최종 export 생성

## GET /exports/:id

export 결과 조회

---

# 10. MVP 성공 기준

## 정량 목표

* 45분 내외 에피소드 1개 기준
* 후보 Shorts **10개 이상 자동 생성**
* 그중 운영자가 **실제로 살릴 만한 후보 3개 이상**
* 초안 1개 수동 편집 시간 **10분 이내**
* 에피소드 업로드 후 첫 후보 확인까지 **15분 이내 목표**

## 정성 목표

* 운영자가 “쓸만한 후보 찾는 시간”이 확실히 줄어야 함
* 단순 줄거리형이 아니라 “해설형” 초안이 나와야 함
* 같은 에피소드 안에서도 후보들이 너무 비슷하지 않아야 함

---

# 11. 1차 개발 우선순위

## P0

* 업로드
* 전처리
* 장면 분할
* 대사 추출
* 후보 추출
* 스크립트 생성
* draft 렌더
* export

## P1

* risk score
* 후보 비교 화면
* TTS 재생성
* 자막 편집
* 템플릿 3종

## P2

* 화자 분리 개선
* 얼굴/표정 기반 점수 강화
* 유사도 중복 방지 강화
* 성과 데이터 기반 후보 점수 재학습

---

# 12. 4주 MVP 개발 플랜

## 1주차

* 프로젝트 세팅
* 업로드/스토리지
* ffmpeg 전처리
* episode/job 모델 설계

## 2주차

* 장면 분할
* transcript 추출
* 후보 생성 로직 v1
* 대시보드 기본 화면

## 3주차

* LLM 스크립트 생성
* TTS 생성
* 세로형 draft 렌더러 v1

## 4주차

* 후보 상세/검수 화면
* export
* risk score
* 실사용 테스트 및 튜닝

---

# 13. 가장 중요한 제품 원칙

이 툴은 **“클립 자동 생산기”**가 아니라
**“해설형 Shorts 초안 제작기”**여야 한다.

즉 평가 기준도 이렇게 잡아야 한다.

나쁜 출력:

* 드라마 줄거리만 요약
* 원본 장면 비중이 너무 큼
* 후보들이 서로 너무 비슷함

좋은 출력:

* 맥락/뉘앙스/심리 해설이 중심
* 운영자가 고를 만한 후보가 여럿 나옴
* 초안에서 손볼 포인트가 명확함

---

DB: PostgreSQL
Backend: FastAPI
Queue: Celery + Redis
Storage: S3 호환 스토리지 또는 로컬
Frontend: Next.js App Router
단일 운영자 중심의 내부 툴
멀티테넌시는 아직 없음
업로드 → 분석 → 후보 생성 → 초안 렌더 → 검수 → export 흐름
1. 전체 구조 요약

핵심 엔티티는 8개다.

episodes: 업로드된 원본 에피소드
jobs: 분석/렌더/export 작업 상태
shots: 장면 분할 결과
transcript_segments: 대사/자막 세그먼트
candidates: Shorts 후보 구간
script_drafts: 후보별 스크립트 초안
video_drafts: 렌더된 초안 영상
exports: 최종 결과물

관계는 이렇게 본다.

episode 1개 → shots 여러 개
episode 1개 → transcript_segments 여러 개
episode 1개 → candidates 여러 개
candidate 1개 → script_drafts 여러 개
candidate 1개 → video_drafts 여러 개
video_draft 1개 → exports 여러 개 가능
모든 비동기 작업은 jobs에 기록

------------------------------------------------------------------------------------------------------------------------------


전제

* DB: **PostgreSQL**
* Backend: **FastAPI**
* Queue: **Celery + Redis**
* Storage: **S3 호환 스토리지 또는 로컬**
* Frontend: **Next.js App Router**
* 단일 운영자 중심의 내부 툴
* 멀티테넌시는 아직 없음
* 업로드 → 분석 → 후보 생성 → 초안 렌더 → 검수 → export 흐름

---

# 1. 전체 구조 요약

핵심 엔티티는 8개다.

* `episodes`: 업로드된 원본 에피소드
* `jobs`: 분석/렌더/export 작업 상태
* `shots`: 장면 분할 결과
* `transcript_segments`: 대사/자막 세그먼트
* `candidates`: Shorts 후보 구간
* `script_drafts`: 후보별 스크립트 초안
* `video_drafts`: 렌더된 초안 영상
* `exports`: 최종 결과물

관계는 이렇게 본다.

* `episode` 1개 → `shots` 여러 개
* `episode` 1개 → `transcript_segments` 여러 개
* `episode` 1개 → `candidates` 여러 개
* `candidate` 1개 → `script_drafts` 여러 개
* `candidate` 1개 → `video_drafts` 여러 개
* `video_draft` 1개 → `exports` 여러 개 가능
* 모든 비동기 작업은 `jobs`에 기록

---

# 2. DB 스키마 SQL 초안

아래는 PostgreSQL 기준이다.

## 2-1. enum / 기본 확장

```sql
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_trgm;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'episode_status') THEN
        CREATE TYPE episode_status AS ENUM (
            'uploaded',
            'processing',
            'ready',
            'failed',
            'archived'
        );
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'job_type') THEN
        CREATE TYPE job_type AS ENUM (
            'ingest',
            'transcode',
            'shot_detection',
            'transcript',
            'candidate_generation',
            'script_generation',
            'draft_render',
            'export_render'
        );
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'job_status') THEN
        CREATE TYPE job_status AS ENUM (
            'queued',
            'running',
            'succeeded',
            'failed',
            'cancelled'
        );
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'candidate_type') THEN
        CREATE TYPE candidate_type AS ENUM (
            'context_commentary',
            'nuance_translation',
            'psychology_analysis'
        );
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'candidate_status') THEN
        CREATE TYPE candidate_status AS ENUM (
            'generated',
            'selected',
            'rejected',
            'drafted',
            'archived'
        );
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'draft_status') THEN
        CREATE TYPE draft_status AS ENUM (
            'created',
            'rendering',
            'ready',
            'failed',
            'approved',
            'rejected'
        );
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'export_status') THEN
        CREATE TYPE export_status AS ENUM (
            'queued',
            'rendering',
            'ready',
            'failed'
        );
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'source_type') THEN
        CREATE TYPE source_type AS ENUM (
            'subtitle',
            'asr',
            'manual'
        );
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'target_channel_type') THEN
        CREATE TYPE target_channel_type AS ENUM (
            'kr_us_drama',
            'us_kr_drama'
        );
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'language_code') THEN
        CREATE TYPE language_code AS ENUM (
            'ko',
            'en'
        );
    END IF;
END
$$;
```

---

## 2-2. episodes

```sql
CREATE TABLE episodes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    show_title VARCHAR(255) NOT NULL,
    season_number INTEGER,
    episode_number INTEGER,
    episode_title VARCHAR(255),
    original_language language_code NOT NULL,
    target_channel target_channel_type NOT NULL,
    source_video_path TEXT NOT NULL,
    proxy_video_path TEXT,
    source_subtitle_path TEXT,
    duration_seconds NUMERIC(10,3),
    fps NUMERIC(8,3),
    width INTEGER,
    height INTEGER,
    file_size_bytes BIGINT,
    checksum_sha256 VARCHAR(64),
    status episode_status NOT NULL DEFAULT 'uploaded',
    error_message TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_episodes_status ON episodes(status);
CREATE INDEX idx_episodes_show_title_trgm ON episodes USING gin (show_title gin_trgm_ops);
```

---

## 2-3. jobs

```sql
CREATE TABLE jobs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    episode_id UUID REFERENCES episodes(id) ON DELETE CASCADE,
    candidate_id UUID,
    video_draft_id UUID,
    export_id UUID,
    celery_task_id VARCHAR(255),
    type job_type NOT NULL,
    status job_status NOT NULL DEFAULT 'queued',
    progress_percent INTEGER NOT NULL DEFAULT 0 CHECK (progress_percent >= 0 AND progress_percent <= 100),
    input_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    output_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_message TEXT,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_jobs_episode_id ON jobs(episode_id);
CREATE INDEX idx_jobs_status ON jobs(status);
CREATE INDEX idx_jobs_type ON jobs(type);
CREATE INDEX idx_jobs_celery_task_id ON jobs(celery_task_id);
```

후에 FK 순환 방지 때문에 `candidate_id`, `video_draft_id`, `export_id`는 뒤에서 FK 추가하는 쪽이 깔끔하다.

---

## 2-4. shots

```sql
CREATE TABLE shots (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    episode_id UUID NOT NULL REFERENCES episodes(id) ON DELETE CASCADE,
    shot_index INTEGER NOT NULL,
    start_time NUMERIC(10,3) NOT NULL,
    end_time NUMERIC(10,3) NOT NULL,
    duration_seconds NUMERIC(10,3) GENERATED ALWAYS AS (end_time - start_time) STORED,
    thumbnail_path TEXT,
    keyframe_path TEXT,
    face_count INTEGER,
    motion_score NUMERIC(6,3),
    closeup_score NUMERIC(6,3),
    emotion_intensity_score NUMERIC(6,3),
    text_safe_area_score NUMERIC(6,3),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (episode_id, shot_index)
);

CREATE INDEX idx_shots_episode_id ON shots(episode_id);
CREATE INDEX idx_shots_start_time ON shots(episode_id, start_time);
```

---

## 2-5. transcript_segments

```sql
CREATE TABLE transcript_segments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    episode_id UUID NOT NULL REFERENCES episodes(id) ON DELETE CASCADE,
    segment_index INTEGER NOT NULL,
    start_time NUMERIC(10,3) NOT NULL,
    end_time NUMERIC(10,3) NOT NULL,
    text TEXT NOT NULL,
    normalized_text TEXT,
    speaker_label VARCHAR(100),
    source source_type NOT NULL,
    confidence NUMERIC(6,3),
    language language_code NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (episode_id, segment_index, source)
);

CREATE INDEX idx_transcript_episode_id ON transcript_segments(episode_id);
CREATE INDEX idx_transcript_time ON transcript_segments(episode_id, start_time);
CREATE INDEX idx_transcript_text_trgm ON transcript_segments USING gin (text gin_trgm_ops);
```

---

## 2-6. candidates

```sql
CREATE TABLE candidates (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    episode_id UUID NOT NULL REFERENCES episodes(id) ON DELETE CASCADE,
    candidate_index INTEGER NOT NULL,
    type candidate_type NOT NULL,
    status candidate_status NOT NULL DEFAULT 'generated',
    title_hint VARCHAR(255),
    start_time NUMERIC(10,3) NOT NULL,
    end_time NUMERIC(10,3) NOT NULL,
    duration_seconds NUMERIC(10,3) GENERATED ALWAYS AS (end_time - start_time) STORED,

    total_score NUMERIC(6,3) NOT NULL DEFAULT 0,
    hook_score NUMERIC(6,3) NOT NULL DEFAULT 0,
    clarity_score NUMERIC(6,3) NOT NULL DEFAULT 0,
    tension_score NUMERIC(6,3) NOT NULL DEFAULT 0,
    emotion_score NUMERIC(6,3) NOT NULL DEFAULT 0,
    commentary_score NUMERIC(6,3) NOT NULL DEFAULT 0,
    visual_score NUMERIC(6,3) NOT NULL DEFAULT 0,
    source_dependence_penalty NUMERIC(6,3) NOT NULL DEFAULT 0,
    repetition_penalty NUMERIC(6,3) NOT NULL DEFAULT 0,

    risk_score NUMERIC(6,3) NOT NULL DEFAULT 0,
    risk_level VARCHAR(20) NOT NULL DEFAULT 'medium',

    shot_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    transcript_segment_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (episode_id, candidate_index)
);

CREATE INDEX idx_candidates_episode_id ON candidates(episode_id);
CREATE INDEX idx_candidates_status ON candidates(status);
CREATE INDEX idx_candidates_total_score ON candidates(total_score DESC);
CREATE INDEX idx_candidates_type ON candidates(type);
CREATE INDEX idx_candidates_risk_level ON candidates(risk_level);
```

---

## 2-7. script_drafts

```sql
CREATE TABLE script_drafts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    candidate_id UUID NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
    version_no INTEGER NOT NULL DEFAULT 1,
    language language_code NOT NULL,
    hook_text TEXT NOT NULL,
    intro_text TEXT,
    body_text TEXT NOT NULL,
    outro_text TEXT,
    cta_text TEXT,
    full_script_text TEXT NOT NULL,
    estimated_duration_seconds NUMERIC(10,3),
    title_options JSONB NOT NULL DEFAULT '[]'::jsonb,
    hook_options JSONB NOT NULL DEFAULT '[]'::jsonb,
    cta_options JSONB NOT NULL DEFAULT '[]'::jsonb,
    commentary_density_score NUMERIC(6,3) NOT NULL DEFAULT 0,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_selected BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (candidate_id, version_no)
);

CREATE INDEX idx_script_drafts_candidate_id ON script_drafts(candidate_id);
CREATE INDEX idx_script_drafts_selected ON script_drafts(candidate_id, is_selected);
```

---

## 2-8. video_drafts

```sql
CREATE TABLE video_drafts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    candidate_id UUID NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
    script_draft_id UUID NOT NULL REFERENCES script_drafts(id) ON DELETE CASCADE,
    version_no INTEGER NOT NULL DEFAULT 1,
    status draft_status NOT NULL DEFAULT 'created',
    template_type VARCHAR(50) NOT NULL,
    tts_voice_key VARCHAR(100),
    aspect_ratio VARCHAR(20) NOT NULL DEFAULT '9:16',
    width INTEGER NOT NULL DEFAULT 1080,
    height INTEGER NOT NULL DEFAULT 1920,
    draft_video_path TEXT,
    subtitle_path TEXT,
    waveform_path TEXT,
    thumbnail_path TEXT,
    burned_caption BOOLEAN NOT NULL DEFAULT TRUE,
    render_config JSONB NOT NULL DEFAULT '{}'::jsonb,
    timeline_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    operator_notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (candidate_id, version_no)
);

CREATE INDEX idx_video_drafts_candidate_id ON video_drafts(candidate_id);
CREATE INDEX idx_video_drafts_script_draft_id ON video_drafts(script_draft_id);
CREATE INDEX idx_video_drafts_status ON video_drafts(status);
```

---

## 2-9. exports

```sql
CREATE TABLE exports (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    video_draft_id UUID NOT NULL REFERENCES video_drafts(id) ON DELETE CASCADE,
    status export_status NOT NULL DEFAULT 'queued',
    export_video_path TEXT,
    export_subtitle_path TEXT,
    export_script_path TEXT,
    export_metadata_path TEXT,
    export_preset VARCHAR(50) NOT NULL DEFAULT 'shorts_default',
    file_size_bytes BIGINT,
    checksum_sha256 VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ
);

CREATE INDEX idx_exports_video_draft_id ON exports(video_draft_id);
CREATE INDEX idx_exports_status ON exports(status);
```

---

## 2-10. review_actions

```sql
CREATE TABLE review_actions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    video_draft_id UUID NOT NULL REFERENCES video_drafts(id) ON DELETE CASCADE,
    action_type VARCHAR(50) NOT NULL,
    action_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    note TEXT,
    created_by VARCHAR(100) NOT NULL DEFAULT 'operator',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_review_actions_video_draft_id ON review_actions(video_draft_id);
CREATE INDEX idx_review_actions_action_type ON review_actions(action_type);
```

---

## 2-11. FK 보강 / updated_at 트리거

```sql
ALTER TABLE jobs
    ADD CONSTRAINT fk_jobs_candidate
    FOREIGN KEY (candidate_id) REFERENCES candidates(id) ON DELETE CASCADE;

ALTER TABLE jobs
    ADD CONSTRAINT fk_jobs_video_draft
    FOREIGN KEY (video_draft_id) REFERENCES video_drafts(id) ON DELETE CASCADE;

ALTER TABLE jobs
    ADD CONSTRAINT fk_jobs_export
    FOREIGN KEY (export_id) REFERENCES exports(id) ON DELETE CASCADE;
```

```sql
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_episodes_updated_at
BEFORE UPDATE ON episodes
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_candidates_updated_at
BEFORE UPDATE ON candidates
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_video_drafts_updated_at
BEFORE UPDATE ON video_drafts
FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

---

## 2-12. 추천 보조 뷰

운영화면에서 아주 유용하다.

```sql
CREATE VIEW candidate_overview AS
SELECT
    c.id,
    c.episode_id,
    e.show_title,
    e.season_number,
    e.episode_number,
    c.candidate_index,
    c.type,
    c.status,
    c.title_hint,
    c.start_time,
    c.end_time,
    c.duration_seconds,
    c.total_score,
    c.risk_score,
    c.risk_level,
    (
        SELECT COUNT(*)
        FROM script_drafts sd
        WHERE sd.candidate_id = c.id
    ) AS script_count,
    (
        SELECT COUNT(*)
        FROM video_drafts vd
        WHERE vd.candidate_id = c.id
    ) AS draft_count
FROM candidates c
JOIN episodes e ON e.id = c.episode_id;
```

---

# 3. FastAPI 엔드포인트 상세

아래는 **실무형 REST 설계**다.
업로드/조회/작업 트리거/수정/다운로드가 분리되어 있다.

---

## 3-1. Episodes

## `POST /api/v1/episodes`

에피소드 업로드 등록.

멀티파트 업로드를 기본으로 본다.

### request

* `video_file`: binary
* `subtitle_file`: optional
* `show_title`
* `season_number`
* `episode_number`
* `episode_title`
* `original_language`
* `target_channel`

### response

```json
{
  "id": "5f1f2a6a-6b1b-4fb4-9f2e-9d76df1d5ef8",
  "status": "uploaded",
  "show_title": "Silicon Valley",
  "season_number": 1,
  "episode_number": 3,
  "target_channel": "kr_us_drama",
  "created_at": "2026-03-23T09:00:00Z"
}
```

---

## `GET /api/v1/episodes`

목록 조회.

### query params

* `status`
* `show_title`
* `page`
* `page_size`

### response

```json
{
  "items": [
    {
      "id": "uuid",
      "show_title": "Silicon Valley",
      "episode_title": "Articles of Incorporation",
      "status": "ready",
      "duration_seconds": 1734.21,
      "created_at": "2026-03-23T09:00:00Z"
    }
  ],
  "page": 1,
  "page_size": 20,
  "total": 1
}
```

---

## `GET /api/v1/episodes/{episode_id}`

단건 상세.

### response

```json
{
  "id": "uuid",
  "show_title": "Silicon Valley",
  "season_number": 1,
  "episode_number": 3,
  "episode_title": "Articles of Incorporation",
  "original_language": "en",
  "target_channel": "kr_us_drama",
  "status": "ready",
  "source_video_path": "s3://...",
  "proxy_video_path": "s3://...",
  "duration_seconds": 1734.21,
  "fps": 23.976,
  "width": 1920,
  "height": 1080,
  "metadata": {}
}
```

---

## `POST /api/v1/episodes/{episode_id}/analyze`

분석 파이프라인 시작.

### request

```json
{
  "force_reanalyze": false
}
```

### response

```json
{
  "episode_id": "uuid",
  "job_id": "uuid",
  "status": "queued",
  "message": "Analysis pipeline started"
}
```

---

## `GET /api/v1/episodes/{episode_id}/timeline`

에피소드 타임라인 데이터 조회.

### response

```json
{
  "episode_id": "uuid",
  "shots": [
    {
      "id": "uuid",
      "shot_index": 1,
      "start_time": 0.0,
      "end_time": 2.34,
      "thumbnail_path": "https://..."
    }
  ],
  "transcript_segments": [
    {
      "id": "uuid",
      "start_time": 1.1,
      "end_time": 3.5,
      "text": "We need to pivot.",
      "speaker_label": "spk_1"
    }
  ]
}
```

---

## 3-2. Jobs

## `GET /api/v1/jobs/{job_id}`

단일 작업 상태 조회.

### response

```json
{
  "id": "uuid",
  "type": "candidate_generation",
  "status": "running",
  "progress_percent": 62,
  "started_at": "2026-03-23T09:05:00Z",
  "finished_at": null,
  "error_message": null,
  "output_payload": {}
}
```

---

## `GET /api/v1/episodes/{episode_id}/jobs`

에피소드 관련 작업 목록.

---

## 3-3. Candidates

## `GET /api/v1/episodes/{episode_id}/candidates`

후보 리스트 조회.

### query params

* `type`
* `status`
* `risk_level`
* `min_score`
* `sort_by=total_score|risk_score|start_time`
* `order=asc|desc`

### response

```json
{
  "items": [
    {
      "id": "uuid",
      "candidate_index": 1,
      "type": "context_commentary",
      "status": "generated",
      "title_hint": "미국 회사에서 이 말은 칭찬이 아니다",
      "start_time": 321.44,
      "end_time": 347.20,
      "duration_seconds": 25.76,
      "total_score": 8.91,
      "risk_score": 3.20,
      "risk_level": "low"
    }
  ],
  "total": 18
}
```

---

## `GET /api/v1/candidates/{candidate_id}`

후보 상세 조회.

### response

```json
{
  "id": "uuid",
  "episode_id": "uuid",
  "type": "context_commentary",
  "status": "generated",
  "title_hint": "미국 회사에서 이 말은 칭찬이 아니다",
  "start_time": 321.44,
  "end_time": 347.20,
  "duration_seconds": 25.76,
  "scores": {
    "total_score": 8.91,
    "hook_score": 9.10,
    "clarity_score": 8.20,
    "tension_score": 7.80,
    "emotion_score": 7.30,
    "commentary_score": 9.40,
    "visual_score": 8.00
  },
  "risk": {
    "risk_score": 3.2,
    "risk_level": "low",
    "reasons": [
      "continuous_clip_max_duration_ok",
      "commentary_density_high"
    ]
  },
  "shots": [
    {
      "id": "uuid",
      "start_time": 321.44,
      "end_time": 323.12,
      "thumbnail_path": "https://..."
    }
  ],
  "transcript_segments": [
    {
      "id": "uuid",
      "text": "This is not going well.",
      "start_time": 322.01,
      "end_time": 323.80
    }
  ],
  "metadata": {}
}
```

---

## `POST /api/v1/candidates/{candidate_id}/select`

운영자가 후보를 선택 처리.

### request

```json
{
  "selected": true
}
```

---

## `POST /api/v1/candidates/{candidate_id}/reject`

후보 폐기.

### request

```json
{
  "reason": "too_source_dependent"
}
```

---

## 3-4. Script Drafts

## `POST /api/v1/candidates/{candidate_id}/script-drafts`

스크립트 초안 생성.

### request

```json
{
  "language": "ko",
  "versions": 2,
  "tone": "sharp_explanatory",
  "channel_style": "kr_us_drama",
  "force_regenerate": false
}
```

### response

```json
{
  "candidate_id": "uuid",
  "job_id": "uuid",
  "status": "queued"
}
```

---

## `GET /api/v1/candidates/{candidate_id}/script-drafts`

후보의 스크립트 초안 목록.

### response

```json
{
  "items": [
    {
      "id": "uuid",
      "version_no": 1,
      "language": "ko",
      "hook_text": "미국 회사에서 이 말은 칭찬이 아니다",
      "full_script_text": "겉으로는 좋아 보이지만...",
      "estimated_duration_seconds": 24.2,
      "title_options": [
        "미국 회사에서 이 말 들으면 끝난다",
        "실리콘밸리식 돌려까기"
      ],
      "is_selected": false
    }
  ]
}
```

---

## `PATCH /api/v1/script-drafts/{script_draft_id}`

스크립트 수동 수정.

### request

```json
{
  "hook_text": "미국 회사에서 이 말은 사실상 선 긋기다",
  "body_text": "이 장면이 웃긴 건 영어 실력보다...",
  "cta_text": "다음은 미국식 회의 화법 편",
  "title_options": [
    "미국 회사에서 이 말은 칭찬이 아니다",
    "실리콘밸리의 무서운 한마디"
  ]
}
```

---

## `POST /api/v1/script-drafts/{script_draft_id}/select`

스크립트 선택.

---

## 3-5. Video Drafts

## `POST /api/v1/candidates/{candidate_id}/video-drafts`

초안 영상 렌더 시작.

### request

```json
{
  "script_draft_id": "uuid",
  "template_type": "context_commentary_v1",
  "tts_voice_key": "ko_female_01",
  "burned_caption": true
}
```

### response

```json
{
  "candidate_id": "uuid",
  "video_draft_id": "uuid",
  "job_id": "uuid",
  "status": "queued"
}
```

---

## `GET /api/v1/candidates/{candidate_id}/video-drafts`

초안 영상 목록.

---

## `GET /api/v1/video-drafts/{video_draft_id}`

초안 영상 상세.

### response

```json
{
  "id": "uuid",
  "candidate_id": "uuid",
  "script_draft_id": "uuid",
  "status": "ready",
  "template_type": "context_commentary_v1",
  "tts_voice_key": "ko_female_01",
  "draft_video_path": "https://...",
  "subtitle_path": "https://...",
  "thumbnail_path": "https://...",
  "timeline_json": {
    "tracks": []
  },
  "render_config": {
    "zoom": true,
    "freeze_frame": true
  }
}
```

---

## `PATCH /api/v1/video-drafts/{video_draft_id}`

수정 가능한 편집 옵션 업데이트.

### request

```json
{
  "operator_notes": "첫 훅 문장 더 세게 수정",
  "timeline_json": {
    "tracks": [
      {
        "type": "video",
        "clips": []
      }
    ]
  },
  "render_config": {
    "hook_font_size": 74,
    "caption_style": "bold_yellow"
  }
}
```

---

## `POST /api/v1/video-drafts/{video_draft_id}/rerender`

수정된 초안 재렌더.

---

## `POST /api/v1/video-drafts/{video_draft_id}/approve`

운영자가 승인 처리.

### request

```json
{
  "note": "export 진행"
}
```

---

## `POST /api/v1/video-drafts/{video_draft_id}/reject`

초안 폐기.

---

## 3-6. Exports

## `POST /api/v1/video-drafts/{video_draft_id}/exports`

최종 결과물 export 생성.

### request

```json
{
  "export_preset": "shorts_default",
  "include_srt": true,
  "include_script_txt": true,
  "include_metadata_json": true
}
```

### response

```json
{
  "export_id": "uuid",
  "job_id": "uuid",
  "status": "queued"
}
```

---

## `GET /api/v1/exports/{export_id}`

export 상태 조회.

### response

```json
{
  "id": "uuid",
  "status": "ready",
  "export_video_path": "https://...",
  "export_subtitle_path": "https://...",
  "export_script_path": "https://...",
  "export_metadata_path": "https://..."
}
```

---

## 3-7. Search / Utility

## `GET /api/v1/search/transcript`

대사 검색.

### query params

* `episode_id`
* `q`

### response

```json
{
  "items": [
    {
      "segment_id": "uuid",
      "text": "We need to pivot.",
      "start_time": 421.11,
      "end_time": 422.80
    }
  ]
}
```

---

## 3-8. FastAPI Pydantic 모델 예시

```python
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime

class EpisodeOut(BaseModel):
    id: UUID
    show_title: str
    season_number: Optional[int] = None
    episode_number: Optional[int] = None
    episode_title: Optional[str] = None
    original_language: str
    target_channel: str
    status: str
    duration_seconds: Optional[float] = None
    created_at: datetime

class CandidateScoreOut(BaseModel):
    total_score: float
    hook_score: float
    clarity_score: float
    tension_score: float
    emotion_score: float
    commentary_score: float
    visual_score: float

class CandidateOut(BaseModel):
    id: UUID
    episode_id: UUID
    type: str
    status: str
    title_hint: Optional[str] = None
    start_time: float
    end_time: float
    duration_seconds: float
    risk_score: float
    risk_level: str
    scores: CandidateScoreOut
```

---

# 4. Celery 작업 플로우

여기서는 **완전 중요한 부분**만 정확히 잡겠다.

핵심 원칙은 이거다.

* 한 작업이 너무 커지면 안 된다
* 작업은 **체인(chain)** 으로 쪼갠다
* 실패 시 어느 단계에서 죽었는지 명확해야 한다
* DB `jobs`와 Celery task 상태가 항상 동기화되어야 한다

---

## 4-1. 전체 파이프라인

분석 파이프라인:

1. `ingest_episode`
2. `transcode_proxy`
3. `detect_shots`
4. `extract_or_generate_transcript`
5. `compute_signals`
6. `generate_candidates`

후보별 제작 파이프라인:

7. `generate_script_drafts`
8. `synthesize_tts`
9. `build_timeline`
10. `render_video_draft`

최종 export 파이프라인:

11. `render_export_assets`

---

## 4-2. Celery 체인 구조

## 분석 체인

```python
chain(
    ingest_episode.s(episode_id),
    transcode_proxy.s(),
    detect_shots.s(),
    extract_or_generate_transcript.s(),
    compute_signals.s(),
    generate_candidates.s()
).apply_async()
```

---

## 스크립트 생성

```python
generate_script_drafts.delay(candidate_id, language="ko", versions=2)
```

---

## 초안 렌더

```python
chain(
    synthesize_tts.s(video_draft_id),
    build_timeline.s(),
    render_video_draft.s()
).apply_async()
```

---

## export 렌더

```python
render_export_assets.delay(export_id)
```

---

## 4-3. 태스크별 입출력

## `ingest_episode(episode_id)`

역할:

* 업로드 파일 존재 확인
* 메타정보 추출
* episodes 업데이트
* job 생성/상태 업데이트

입력:

* `episode_id`

출력:

* `{ "episode_id": ..., "source_video_path": ... }`

실패 조건:

* 파일 없음
* ffprobe 실패

---

## `transcode_proxy(payload)`

역할:

* 프록시 mp4 생성
* 프레임레이트/코덱 통일
* 오디오 추출

출력:

```json
{
  "episode_id": "uuid",
  "proxy_video_path": "s3://...",
  "audio_path": "s3://..."
}
```

---

## `detect_shots(payload)`

역할:

* 컷 탐지
* 대표 프레임 추출
* `shots` insert

출력:

```json
{
  "episode_id": "uuid",
  "shot_count": 482
}
```

---

## `extract_or_generate_transcript(payload)`

역할:

* subtitle 있으면 우선 ingest
* 없으면 ASR
* transcript 정렬 후 insert

출력:

```json
{
  "episode_id": "uuid",
  "transcript_segment_count": 912
}
```

---

## `compute_signals(payload)`

역할:

* 감정/갈등/클로즈업/시각적 명료성 계산
* shot metadata 갱신

출력:

```json
{
  "episode_id": "uuid",
  "signal_status": "done"
}
```

---

## `generate_candidates(payload)`

역할:

* shot + transcript 조합으로 후보 구간 생성
* 점수 계산
* 중복 필터링
* `candidates` insert

출력:

```json
{
  "episode_id": "uuid",
  "candidate_count": 18
}
```

---

## `generate_script_drafts(candidate_id, language, versions)`

역할:

* 후보 1개에 대해 LLM 기반 스크립트 n개 생성
* title/hook/cta 포함
* `script_drafts` insert

출력:

```json
{
  "candidate_id": "uuid",
  "script_draft_ids": ["uuid1", "uuid2"]
}
```

---

## `synthesize_tts(video_draft_id)`

역할:

* 선택 script를 음성으로 생성
* 문장별 타이밍 추정

---

## `build_timeline(payload)`

역할:

* template type에 맞게 timeline_json 생성
* clip in/out, overlays, captions, freeze, zoom 등 확정

---

## `render_video_draft(payload)`

역할:

* ffmpeg로 세로형 draft 렌더
* `video_drafts.status = ready`

---

## `render_export_assets(export_id)`

역할:

* 최종 mp4 렌더
* srt/txt/json 생성
* `exports.status = ready`

---

## 4-4. 작업 상태 머신

## Episode

* `uploaded`
* `processing`
* `ready`
* `failed`

## Job

* `queued`
* `running`
* `succeeded`
* `failed`
* `cancelled`

## Candidate

* `generated`
* `selected`
* `rejected`
* `drafted`

## VideoDraft

* `created`
* `rendering`
* `ready`
* `approved`
* `rejected`

## Export

* `queued`
* `rendering`
* `ready`
* `failed`

---

## 4-5. Celery 라우팅 전략

큐를 최소 3개로 나누는 게 좋다.

* `cpu_queue`

  * shot detection
  * transcript alignment
  * scoring
* `io_queue`

  * upload, download, file ops
* `gpu_or_heavy_queue`

  * ASR
  * rendering
  * tts large model

예:

```python
task_routes = {
    "tasks.ingest_episode": {"queue": "io_queue"},
    "tasks.transcode_proxy": {"queue": "cpu_queue"},
    "tasks.detect_shots": {"queue": "cpu_queue"},
    "tasks.extract_or_generate_transcript": {"queue": "gpu_or_heavy_queue"},
    "tasks.generate_script_drafts": {"queue": "cpu_queue"},
    "tasks.render_video_draft": {"queue": "gpu_or_heavy_queue"},
}
```

---

## 4-6. 실패 처리 원칙

* 각 task 시작 시 `jobs.status = running`
* 성공 시 `succeeded`
* 예외 시 `failed`, `error_message` 기록
* 상위 객체도 동기화

  * 분석 실패 시 `episodes.status = failed`
  * draft 렌더 실패 시 `video_drafts.status = failed`

재시도는 아래만 허용 권장:

* 네트워크 업로드/다운로드
* TTS provider timeout
* ASR timeout

재시도 비권장:

* 잘못된 ffmpeg 인자
* 스크립트 파싱 실패
* 파일 포맷 손상

---

# 5. Next.js 운영화면 와이어프레임

여기는 **실제로 운영자가 하루 종일 볼 화면**이므로 단순해야 한다.

App Router 기준 추천 구조:

```txt
/app
  /episodes
    /page.tsx
    /new/page.tsx
    /[episodeId]/page.tsx
    /[episodeId]/candidates/page.tsx
  /candidates
    /[candidateId]/page.tsx
  /drafts
    /[draftId]/page.tsx
  /exports
    /[exportId]/page.tsx
```

---

## 5-1. 화면 1: 에피소드 목록

경로: `/episodes`

목적:

* 업로드된 에피소드 상태 확인
* 새 분석 시작
* 기존 작업 재진입

### 와이어프레임

```txt
┌─────────────────────────────────────────────────────────────────────┐
│ Drama Shorts Copilot                                  [New Upload] │
├─────────────────────────────────────────────────────────────────────┤
│ Filters: [Status ▼] [Target Channel ▼] [Search Show Title_______]  │
├─────────────────────────────────────────────────────────────────────┤
│ Show Title        S/E     Target         Status      Duration       │
│ Silicon Valley    1/3     KR←US          READY       28m 54s        │
│ My Mister         1/5     US←KR          PROCESSING  63m 12s        │
│ Hospital Playlist 2/1     US←KR          FAILED      75m 03s        │
├─────────────────────────────────────────────────────────────────────┤
│ [Open] [Reanalyze] [Delete]                                        │
└─────────────────────────────────────────────────────────────────────┘
```

### 핵심 컴포넌트

* 검색창
* 상태 배지
* 업로드 버튼
* 행 단위 액션

---

## 5-2. 화면 2: 에피소드 업로드

경로: `/episodes/new`

### 와이어프레임

```txt
┌────────────────────────────────────────────┐
│ New Episode Upload                         │
├────────────────────────────────────────────┤
│ Show Title          [___________________]  │
│ Season Number       [___]                  │
│ Episode Number      [___]                  │
│ Episode Title       [___________________]  │
│ Original Language   [EN ▼]                 │
│ Target Channel      [KR←US ▼]              │
│ Video File          [Choose File]          │
│ Subtitle File       [Choose File]          │
│                                            │
│                            [Upload & Save] │
└────────────────────────────────────────────┘
```

---

## 5-3. 화면 3: 에피소드 상세

경로: `/episodes/[episodeId]`

목적:

* 분석 상태
* shot/transcript timeline
* 다음 단계 진입

### 와이어프레임

```txt
┌───────────────────────────────────────────────────────────────────────────┐
│ Silicon Valley S1E3                               [Analyze] [Candidates] │
├───────────────────────────────────────────────────────────────────────────┤
│ Status: READY   Duration: 28m54s   Target: KR←US                         │
│ Jobs: ingest ✓  transcode ✓  shots ✓  transcript ✓  candidates ✓         │
├───────────────────────────────────────────────────────────────────────────┤
│ Video Preview                                                             │
│ ┌───────────────────────────────────────────────────────────────────────┐ │
│ │                         proxy player                                  │ │
│ └───────────────────────────────────────────────────────────────────────┘ │
├───────────────────────────────────────────────────────────────────────────┤
│ Timeline                                                                  │
│ [shot bars................................................................]│
│ [transcript markers.......................................................]│
├───────────────────────────────────────────────────────────────────────────┤
│ Transcript Search [________________]                                      │
│ 421.11  "We need to pivot."                                               │
│ 422.80  "This is not good."                                               │
└───────────────────────────────────────────────────────────────────────────┘
```

### 추천 UI 컴포넌트

* video player
* horizontal timeline
* searchable transcript panel
* job progress strip

---

## 5-4. 화면 4: 후보 리스트

경로: `/episodes/[episodeId]/candidates`

이 화면이 핵심이다.

### 와이어프레임

```txt
┌──────────────────────────────────────────────────────────────────────────────┐
│ Candidates - Silicon Valley S1E3                                            │
├──────────────────────────────────────────────────────────────────────────────┤
│ Filters: [Type ▼] [Risk ▼] [Min Score ▼] [Sort ▼]                          │
├──────────────────────────────────────────────────────────────────────────────┤
│ [Thumb]  #1  context_commentary                                             │
│ 05:21 - 05:47 | Score 8.91 | Risk LOW                                       │
│ "미국 회사에서 이 말은 칭찬이 아니다"                                         │
│ [Preview] [Generate Scripts] [Select] [Reject]                              │
├──────────────────────────────────────────────────────────────────────────────┤
│ [Thumb]  #2  nuance_translation                                             │
│ 13:01 - 13:28 | Score 8.37 | Risk MEDIUM                                    │
│ "겉으론 polite인데 실제론 냉정한 표현"                                       │
│ [Preview] [Generate Scripts] [Select] [Reject]                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 카드에 꼭 보여줘야 할 것

* 썸네일
* 길이
* 점수
* 리스크
* title hint
* 액션 버튼

---

## 5-5. 화면 5: 후보 상세

경로: `/candidates/[candidateId]`

목적:

* 후보의 품질 판단
* 스크립트 생성/선택
* draft 생성 시작

### 와이어프레임

```txt
┌──────────────────────────────────────────────────────────────────────────────┐
│ Candidate #1                                                               │
├──────────────────────────────────────────────────────────────────────────────┤
│ Time: 05:21 - 05:47 | Type: context_commentary | Score: 8.91 | Risk: LOW   │
├──────────────────────────────────────────────────────────────────────────────┤
│ Preview                                                                     │
│ ┌──────────────────────────────┐  Shot List                                 │
│ │ candidate clip player        │  1. 05:21~05:23                            │
│ │                              │  2. 05:24~05:25                            │
│ └──────────────────────────────┘  3. 05:26~05:28                            │
├──────────────────────────────────────────────────────────────────────────────┤
│ Scores                                                                      │
│ Hook 9.1 / Clarity 8.2 / Commentary 9.4 / Visual 8.0                        │
├──────────────────────────────────────────────────────────────────────────────┤
│ Transcript excerpt                                                          │
│ "We need to pivot..."                                                       │
├──────────────────────────────────────────────────────────────────────────────┤
│ [Generate Script Drafts]                                                    │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 5-6. 화면 6: 스크립트 선택 + 편집

경로: `/candidates/[candidateId]` 내부 탭 또는 `/script-drafts/[id]`

### 와이어프레임

```txt
┌──────────────────────────────────────────────────────────────────────────────┐
│ Script Drafts                                                               │
├──────────────────────────────────────────────────────────────────────────────┤
│ Version 1                                                                   │
│ Hook: 미국 회사에서 이 말은 칭찬이 아니다                                     │
│ Body: 이 장면이 웃긴 건 영어가 아니라...                                      │
│ CTA : 다음은 실리콘밸리식 회의 화법 편                                        │
│ Titles: [ ... ]                                                             │
│ [Select] [Edit]                                                             │
├──────────────────────────────────────────────────────────────────────────────┤
│ Version 2                                                                   │
│ Hook: 미국 직장인이 웃으면서 선 긋는 방법                                     │
│ ...                                                                         │
│ [Select] [Edit]                                                             │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 5-7. 화면 7: Draft Editor

경로: `/drafts/[draftId]`

이게 실제 편집자 메인 화면이다.

### 와이어프레임

```txt
┌────────────────────────────────────────────────────────────────────────────────────┐
│ Draft Editor                                                       [Rerender] [Approve] │
├────────────────────────────────────────────────────────────────────────────────────┤
│ Left: Video Preview                  │ Right: Controls                                 │
│ ┌─────────────────────────────────┐ │ Hook Text                                        │
│ │      9:16 preview player        │ │ [___________________________________________]     │
│ │                                 │ │ Body Script                                      │
│ │                                 │ │ [___________________________________________]     │
│ └─────────────────────────────────┘ │ [___________________________________________]     │
│                                     │ CTA                                              │
│ Timeline                            │ [___________________________________________]     │
│ [clip][clip][freeze][caption]       │                                                  │
│ [voice track....................]   │ Template [context_commentary_v1 ▼]              │
│ [caption track..................]   │ TTS Voice [ko_female_01 ▼]                       │
│                                     │ Caption Style [bold_yellow ▼]                    │
│                                     │                                                  │
│                                     │ [Regenerate TTS] [Save]                          │
├────────────────────────────────────────────────────────────────────────────────────┤
│ Notes / Review History                                                                 │
└────────────────────────────────────────────────────────────────────────────────────┘
```

### 꼭 필요한 인터랙션

* 훅 텍스트 수정
* 본문 수정
* CTA 수정
* TTS 재생성
* 렌더 재실행
* 상태 승인

---

## 5-8. 화면 8: Export 센터

경로: `/exports/[exportId]`

### 와이어프레임

```txt
┌────────────────────────────────────────────────────────────┐
│ Export Result                                             │
├────────────────────────────────────────────────────────────┤
│ Status: READY                                             │
│ Video: [Download MP4]                                     │
│ Subtitle: [Download SRT]                                  │
│ Script: [Download TXT]                                    │
│ Metadata: [Download JSON]                                 │
│                                                            │
│ Preview                                                    │
│ ┌──────────────────────────────────────────────────────┐   │
│ │                   video player                       │   │
│ └──────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────┘
```

---

# 6. Next.js 컴포넌트 구조 추천

## 공통

* `EpisodeTable`
* `StatusBadge`
* `JobProgressBar`
* `VideoPlayer`
* `TimelineViewer`
* `CandidateCard`
* `ScriptDraftCard`
* `DraftEditorPanel`
* `ExportPanel`

## 상태관리

초기 MVP는:

* 서버 데이터: `TanStack Query`
* local UI state: `useState` / `zustand`

추천 이유:

* 폴링이 많음
* job progress 갱신 필요
* 영상 편집 설정은 draft editor에서만 로컬 상태로 충분

---

# 7. API와 UI 연결 방식

### Episodes 목록

* `GET /episodes`
* 10초 폴링 또는 수동 새로고침

### 분석 진행중 화면

* `GET /jobs/{job_id}`
* 2초 폴링

### 후보 리스트

* `GET /episodes/{episode_id}/candidates`

### 스크립트 생성 버튼

* `POST /candidates/{id}/script-drafts`
* job 생성 후 완료 시 리스트 재조회

### draft 렌더

* `POST /candidates/{id}/video-drafts`
* `GET /video-drafts/{id}` 폴링

### export

* `POST /video-drafts/{id}/exports`
* `GET /exports/{id}` 폴링

---

# 8. 운영상 중요한 실무 포인트

## 1. timeline_json은 충분히 유연하게

처음부터 너무 복잡한 NLE처럼 만들 필요는 없다.
하지만 최소한 아래는 표현 가능해야 한다.

* clip in/out
* crop / zoom
* freeze frame
* text overlay
* subtitle block
* voiceover timing
* transition type

예시:

```json
{
  "tracks": [
    {
      "type": "video",
      "clips": [
        {
          "source": "episode",
          "shot_id": "uuid",
          "in": 321.44,
          "out": 323.10,
          "canvas": {
            "crop": "center",
            "zoom": 1.15
          }
        }
      ]
    },
    {
      "type": "voiceover",
      "items": [
        {
          "start": 0.0,
          "end": 2.5,
          "audio_path": "s3://..."
        }
      ]
    },
    {
      "type": "caption",
      "items": [
        {
          "start": 0.0,
          "end": 2.5,
          "text": "미국 회사에서 이 말은 칭찬이 아니다"
        }
      ]
    }
  ]
}
```

---

## 2. 샷 참조는 JSON보다 조인 테이블이 더 정규화적이지만

MVP에선 `candidates.shot_ids` JSONB로 가도 된다.
속도가 더 중요하다.

다만 나중에 고도화하면 아래로 분리 가능:

* `candidate_shots`
* `candidate_transcript_segments`

---

## 3. review_actions는 반드시 남겨라

운영자 수정 패턴이 쌓이면 나중에 자동 품질 개선에 쓸 수 있다.

예:

* 어떤 훅이 자주 수정되는가
* 어떤 template가 자주 폐기되는가
* 어떤 risk 경고가 실제로 무시되는가

---

## 4. export는 immutable하게

최종 산출물은 수정하지 말고 버전 새로 파는 게 맞다.
그래야 나중에 히스토리와 비교가 된다.

---

# 9. 추천 폴더 / 저장 구조

S3 또는 로컬 공통적으로 이렇게 나누는 게 좋다.

```txt
/episodes/{episode_id}/source/source.mp4
/episodes/{episode_id}/source/source.srt
/episodes/{episode_id}/proxy/proxy.mp4
/episodes/{episode_id}/audio/audio.wav
/episodes/{episode_id}/shots/{shot_index}.jpg
/episodes/{episode_id}/candidates/{candidate_id}/script_drafts/{version}.json
/episodes/{episode_id}/candidates/{candidate_id}/video_drafts/{version}.mp4
/episodes/{episode_id}/candidates/{candidate_id}/exports/{export_id}/final.mp4
/episodes/{episode_id}/candidates/{candidate_id}/exports/{export_id}/final.srt
```

---

# 10. MVP 구현 우선순위

진짜 개발 순서는 이렇게 가는 게 맞다.

## 1단계

* episodes
* jobs
* shots
* transcript_segments
* candidates
* 분석 파이프라인

## 2단계

* script_drafts
* LLM 생성
* 후보 상세 화면

## 3단계

* video_drafts
* TTS
* timeline_json
* ffmpeg 렌더

## 4단계

* exports
* review_actions
* risk warnings
* export 화면

---

# 11. 내가 권하는 다음 작업 순서

이제 바로 다음으로 해야 할 건 3개다.

### A. Alembic 마이그레이션 파일로 쪼개기

* `001_create_enums`
* `002_create_episodes_jobs`
* `003_create_shots_transcripts`
* `004_create_candidates`
* `005_create_script_drafts_video_drafts_exports`

### B. FastAPI 프로젝트 구조 확정

예:

```txt
app/
  api/
    v1/
      episodes.py
      jobs.py
      candidates.py
      script_drafts.py
      video_drafts.py
      exports.py
  core/
    config.py
    db.py
    celery_app.py
  models/
  schemas/
  services/
    ingest_service.py
    candidate_service.py
    script_service.py
    render_service.py
  tasks/
    ingest_tasks.py
    analysis_tasks.py
    render_tasks.py
```

### C. Next.js 기본 페이지부터 깔기

* `/episodes`
* `/episodes/new`
* `/episodes/[id]`
* `/episodes/[id]/candidates`
* `/drafts/[id]`




좋다.
이제는 **바로 프로젝트 골격을 만드는 수준**으로 이어가겠다.

이번 초안은 **SQLAlchemy 2 스타일**로 잡는다. 공식 문서 기준으로 현재 권장되는 선언형 매핑은 `DeclarativeBase`, `Mapped`, `mapped_column` 패턴이고, Alembic은 `env.py`에서 `target_metadata`를 연결해 `--autogenerate`를 쓰는 구성이 기본이다. 또 autogenerate는 모든 변경을 완벽하게 잡아주지는 않으므로, enum/커스텀 타입/복잡한 제약조건은 사람이 마이그레이션을 검토하는 전제를 두는 게 맞다. ([SQLAlchemy Documentation][1])

---

# 1) FastAPI 프로젝트 폴더 구조

```txt
backend/
  alembic.ini
  pyproject.toml
  .env

  alembic/
    env.py
    script.py.mako
    versions/
      001_create_enums.py
      002_create_episodes_jobs.py
      003_create_shots_transcripts.py
      004_create_candidates.py
      005_create_script_drafts_video_drafts_exports.py
      006_create_review_actions_and_indexes.py

  app/
    main.py

    api/
      deps.py
      router.py
      v1/
        episodes.py
        jobs.py
        candidates.py
        script_drafts.py
        video_drafts.py
        exports.py

    core/
      config.py
      db.py
      logging.py
      celery_app.py

    db/
      base.py
      session.py
      enums.py
      models/
        __init__.py
        episode.py
        job.py
        shot.py
        transcript_segment.py
        candidate.py
        script_draft.py
        video_draft.py
        export.py
        review_action.py

    schemas/
      common.py
      episode.py
      job.py
      candidate.py
      script_draft.py
      video_draft.py
      export.py

    services/
      ingest_service.py
      analysis_service.py
      candidate_service.py
      script_service.py
      render_service.py
      storage_service.py

    tasks/
      ingest_tasks.py
      analysis_tasks.py
      render_tasks.py

    utils/
      timecode.py
      ffmpeg.py
      transcript.py
      hashing.py
```

---

# 2) 기본 설정 파일

## `app/core/config.py`

```python
from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "Drama Shorts Copilot"
    APP_ENV: str = "local"
    APP_DEBUG: bool = True

    DATABASE_URL: str = Field(..., description="SQLAlchemy sync URL")
    REDIS_URL: str = Field(..., description="Redis URL for Celery broker/backend")

    STORAGE_BACKEND: str = "local"  # local | s3
    STORAGE_LOCAL_ROOT: str = "./storage"

    S3_BUCKET: str | None = None
    S3_REGION: str | None = None
    S3_ENDPOINT_URL: str | None = None
    S3_ACCESS_KEY_ID: str | None = None
    S3_SECRET_ACCESS_KEY: str | None = None

    DEFAULT_PAGE_SIZE: int = 20
    MAX_PAGE_SIZE: int = 100


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

---

## `app/core/db.py`

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings

settings = get_settings()

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    future=True,
)
```

---

## `app/api/deps.py`

```python
from collections.abc import Generator
from sqlalchemy.orm import Session

from app.core.db import SessionLocal


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

---

## `app/main.py`

```python
from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.APP_NAME,
    debug=settings.APP_DEBUG,
)

app.include_router(api_router, prefix="/api")
```

---

## `app/api/router.py`

```python
from fastapi import APIRouter

from app.api.v1 import episodes, jobs, candidates, script_drafts, video_drafts, exports

api_router = APIRouter()

api_router.include_router(episodes.router, prefix="/v1/episodes", tags=["episodes"])
api_router.include_router(jobs.router, prefix="/v1/jobs", tags=["jobs"])
api_router.include_router(candidates.router, prefix="/v1/candidates", tags=["candidates"])
api_router.include_router(script_drafts.router, prefix="/v1/script-drafts", tags=["script-drafts"])
api_router.include_router(video_drafts.router, prefix="/v1/video-drafts", tags=["video-drafts"])
api_router.include_router(exports.router, prefix="/v1/exports", tags=["exports"])
```

---

# 3) SQLAlchemy Base / Enum / Common Mixins

SQLAlchemy 2 계열에서는 선언형 매핑에 `DeclarativeBase`, `Mapped`, `mapped_column`을 쓰는 패턴이 현재 기준이다. ([SQLAlchemy Documentation][1])

## `app/db/base.py`

```python
from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class UUIDPrimaryKeyMixin:
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
```

---

## `app/db/enums.py`

```python
import enum


class EpisodeStatus(str, enum.Enum):
    uploaded = "uploaded"
    processing = "processing"
    ready = "ready"
    failed = "failed"
    archived = "archived"


class JobType(str, enum.Enum):
    ingest = "ingest"
    transcode = "transcode"
    shot_detection = "shot_detection"
    transcript = "transcript"
    candidate_generation = "candidate_generation"
    script_generation = "script_generation"
    draft_render = "draft_render"
    export_render = "export_render"


class JobStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class CandidateType(str, enum.Enum):
    context_commentary = "context_commentary"
    nuance_translation = "nuance_translation"
    psychology_analysis = "psychology_analysis"


class CandidateStatus(str, enum.Enum):
    generated = "generated"
    selected = "selected"
    rejected = "rejected"
    drafted = "drafted"
    archived = "archived"


class DraftStatus(str, enum.Enum):
    created = "created"
    rendering = "rendering"
    ready = "ready"
    failed = "failed"
    approved = "approved"
    rejected = "rejected"


class ExportStatus(str, enum.Enum):
    queued = "queued"
    rendering = "rendering"
    ready = "ready"
    failed = "failed"


class SourceType(str, enum.Enum):
    subtitle = "subtitle"
    asr = "asr"
    manual = "manual"


class TargetChannelType(str, enum.Enum):
    kr_us_drama = "kr_us_drama"
    us_kr_drama = "us_kr_drama"


class LanguageCode(str, enum.Enum):
    ko = "ko"
    en = "en"
```

---

# 4) SQLAlchemy 모델 초안

## `app/db/models/episode.py`

```python
from __future__ import annotations

from sqlalchemy import BigInteger, Enum, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.enums import EpisodeStatus, LanguageCode, TargetChannelType


class Episode(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "episodes"

    show_title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    season_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    episode_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    episode_title: Mapped[str | None] = mapped_column(String(255), nullable=True)

    original_language: Mapped[LanguageCode] = mapped_column(
        Enum(LanguageCode, name="language_code"),
        nullable=False,
    )
    target_channel: Mapped[TargetChannelType] = mapped_column(
        Enum(TargetChannelType, name="target_channel_type"),
        nullable=False,
    )

    source_video_path: Mapped[str] = mapped_column(Text, nullable=False)
    proxy_video_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_subtitle_path: Mapped[str | None] = mapped_column(Text, nullable=True)

    duration_seconds: Mapped[float | None] = mapped_column(Numeric(10, 3), nullable=True)
    fps: Mapped[float | None] = mapped_column(Numeric(8, 3), nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[EpisodeStatus] = mapped_column(
        Enum(EpisodeStatus, name="episode_status"),
        nullable=False,
        default=EpisodeStatus.uploaded,
        server_default=EpisodeStatus.uploaded.value,
        index=True,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict, server_default="{}")

    jobs = relationship("Job", back_populates="episode", cascade="all, delete-orphan")
    shots = relationship("Shot", back_populates="episode", cascade="all, delete-orphan")
    transcript_segments = relationship("TranscriptSegment", back_populates="episode", cascade="all, delete-orphan")
    candidates = relationship("Candidate", back_populates="episode", cascade="all, delete-orphan")
```

---

## `app/db/models/job.py`

```python
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKeyMixin
from app.db.enums import JobStatus, JobType


class Job(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "jobs"

    episode_id: Mapped[str | None] = mapped_column(UUID(as_uuid=True), ForeignKey("episodes.id", ondelete="CASCADE"))
    candidate_id: Mapped[str | None] = mapped_column(UUID(as_uuid=True), ForeignKey("candidates.id", ondelete="CASCADE"))
    video_draft_id: Mapped[str | None] = mapped_column(UUID(as_uuid=True), ForeignKey("video_drafts.id", ondelete="CASCADE"))
    export_id: Mapped[str | None] = mapped_column(UUID(as_uuid=True), ForeignKey("exports.id", ondelete="CASCADE"))

    celery_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    type: Mapped[JobType] = mapped_column(Enum(JobType, name="job_type"), nullable=False, index=True)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="job_status"),
        nullable=False,
        default=JobStatus.queued,
        server_default=JobStatus.queued.value,
        index=True,
    )
    progress_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    input_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    output_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    episode = relationship("Episode", back_populates="jobs")
    candidate = relationship("Candidate", back_populates="jobs")
    video_draft = relationship("VideoDraft", back_populates="jobs")
    export = relationship("Export", back_populates="jobs")
```

---

## `app/db/models/shot.py`

```python
from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, Numeric, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Shot(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "shots"
    __table_args__ = (
        UniqueConstraint("episode_id", "shot_index", name="uq_shots_episode_shot_index"),
    )

    episode_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("episodes.id", ondelete="CASCADE"), index=True)
    shot_index: Mapped[int] = mapped_column(Integer, nullable=False)

    start_time: Mapped[float] = mapped_column(Numeric(10, 3), nullable=False)
    end_time: Mapped[float] = mapped_column(Numeric(10, 3), nullable=False)

    thumbnail_path: Mapped[str | None] = mapped_column(nullable=True)
    keyframe_path: Mapped[str | None] = mapped_column(nullable=True)

    face_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    motion_score: Mapped[float | None] = mapped_column(Numeric(6, 3), nullable=True)
    closeup_score: Mapped[float | None] = mapped_column(Numeric(6, 3), nullable=True)
    emotion_intensity_score: Mapped[float | None] = mapped_column(Numeric(6, 3), nullable=True)
    text_safe_area_score: Mapped[float | None] = mapped_column(Numeric(6, 3), nullable=True)

    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict, server_default="{}")

    episode = relationship("Episode", back_populates="shots")
```

---

## `app/db/models/transcript_segment.py`

```python
from __future__ import annotations

from sqlalchemy import Enum, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.enums import LanguageCode, SourceType


class TranscriptSegment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "transcript_segments"
    __table_args__ = (
        UniqueConstraint("episode_id", "segment_index", "source", name="uq_transcript_episode_segment_source"),
    )

    episode_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("episodes.id", ondelete="CASCADE"), index=True)
    segment_index: Mapped[int] = mapped_column(Integer, nullable=False)

    start_time: Mapped[float] = mapped_column(Numeric(10, 3), nullable=False)
    end_time: Mapped[float] = mapped_column(Numeric(10, 3), nullable=False)

    text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    speaker_label: Mapped[str | None] = mapped_column(String(100), nullable=True)

    source: Mapped[SourceType] = mapped_column(Enum(SourceType, name="source_type"), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Numeric(6, 3), nullable=True)
    language: Mapped[LanguageCode] = mapped_column(Enum(LanguageCode, name="language_code"), nullable=False)

    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict, server_default="{}")

    episode = relationship("Episode", back_populates="transcript_segments")
```

---

## `app/db/models/candidate.py`

```python
from __future__ import annotations

from sqlalchemy import Enum, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.enums import CandidateStatus, CandidateType


class Candidate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "candidates"
    __table_args__ = (
        UniqueConstraint("episode_id", "candidate_index", name="uq_candidates_episode_candidate_index"),
    )

    episode_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("episodes.id", ondelete="CASCADE"), index=True)
    candidate_index: Mapped[int] = mapped_column(Integer, nullable=False)

    type: Mapped[CandidateType] = mapped_column(Enum(CandidateType, name="candidate_type"), nullable=False, index=True)
    status: Mapped[CandidateStatus] = mapped_column(
        Enum(CandidateStatus, name="candidate_status"),
        nullable=False,
        default=CandidateStatus.generated,
        server_default=CandidateStatus.generated.value,
        index=True,
    )
    title_hint: Mapped[str | None] = mapped_column(String(255), nullable=True)

    start_time: Mapped[float] = mapped_column(Numeric(10, 3), nullable=False)
    end_time: Mapped[float] = mapped_column(Numeric(10, 3), nullable=False)

    total_score: Mapped[float] = mapped_column(Numeric(6, 3), nullable=False, default=0, server_default="0")
    hook_score: Mapped[float] = mapped_column(Numeric(6, 3), nullable=False, default=0, server_default="0")
    clarity_score: Mapped[float] = mapped_column(Numeric(6, 3), nullable=False, default=0, server_default="0")
    tension_score: Mapped[float] = mapped_column(Numeric(6, 3), nullable=False, default=0, server_default="0")
    emotion_score: Mapped[float] = mapped_column(Numeric(6, 3), nullable=False, default=0, server_default="0")
    commentary_score: Mapped[float] = mapped_column(Numeric(6, 3), nullable=False, default=0, server_default="0")
    visual_score: Mapped[float] = mapped_column(Numeric(6, 3), nullable=False, default=0, server_default="0")
    source_dependence_penalty: Mapped[float] = mapped_column(Numeric(6, 3), nullable=False, default=0, server_default="0")
    repetition_penalty: Mapped[float] = mapped_column(Numeric(6, 3), nullable=False, default=0, server_default="0")

    risk_score: Mapped[float] = mapped_column(Numeric(6, 3), nullable=False, default=0, server_default="0")
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False, default="medium", server_default="medium")

    shot_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    transcript_segment_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict, server_default="{}")

    episode = relationship("Episode", back_populates="candidates")
    jobs = relationship("Job", back_populates="candidate")
    script_drafts = relationship("ScriptDraft", back_populates="candidate", cascade="all, delete-orphan")
    video_drafts = relationship("VideoDraft", back_populates="candidate", cascade="all, delete-orphan")
```

---

## `app/db/models/script_draft.py`

```python
from __future__ import annotations

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, Numeric, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.enums import LanguageCode


class ScriptDraft(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "script_drafts"
    __table_args__ = (
        UniqueConstraint("candidate_id", "version_no", name="uq_script_drafts_candidate_version"),
    )

    candidate_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("candidates.id", ondelete="CASCADE"), index=True)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    language: Mapped[LanguageCode] = mapped_column(Enum(LanguageCode, name="language_code"), nullable=False)

    hook_text: Mapped[str] = mapped_column(Text, nullable=False)
    intro_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_text: Mapped[str] = mapped_column(Text, nullable=False)
    outro_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    cta_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    full_script_text: Mapped[str] = mapped_column(Text, nullable=False)

    estimated_duration_seconds: Mapped[float | None] = mapped_column(Numeric(10, 3), nullable=True)

    title_options: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    hook_options: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    cta_options: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")

    commentary_density_score: Mapped[float] = mapped_column(Numeric(6, 3), nullable=False, default=0, server_default="0")
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict, server_default="{}")
    is_selected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    candidate = relationship("Candidate", back_populates="script_drafts")
    video_drafts = relationship("VideoDraft", back_populates="script_draft")
```

---

## `app/db/models/video_draft.py`

```python
from __future__ import annotations

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.enums import DraftStatus


class VideoDraft(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "video_drafts"
    __table_args__ = (
        UniqueConstraint("candidate_id", "version_no", name="uq_video_drafts_candidate_version"),
    )

    candidate_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("candidates.id", ondelete="CASCADE"), index=True)
    script_draft_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("script_drafts.id", ondelete="CASCADE"), index=True)

    version_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    status: Mapped[DraftStatus] = mapped_column(
        Enum(DraftStatus, name="draft_status"),
        nullable=False,
        default=DraftStatus.created,
        server_default=DraftStatus.created.value,
        index=True,
    )

    template_type: Mapped[str] = mapped_column(String(50), nullable=False)
    tts_voice_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    aspect_ratio: Mapped[str] = mapped_column(String(20), nullable=False, default="9:16", server_default="9:16")

    width: Mapped[int] = mapped_column(Integer, nullable=False, default=1080, server_default="1080")
    height: Mapped[int] = mapped_column(Integer, nullable=False, default=1920, server_default="1920")

    draft_video_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    subtitle_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    waveform_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    thumbnail_path: Mapped[str | None] = mapped_column(Text, nullable=True)

    burned_caption: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    render_config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    timeline_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    operator_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    candidate = relationship("Candidate", back_populates="video_drafts")
    script_draft = relationship("ScriptDraft", back_populates="video_drafts")
    exports = relationship("Export", back_populates="video_draft", cascade="all, delete-orphan")
    jobs = relationship("Job", back_populates="video_draft")
    review_actions = relationship("ReviewAction", back_populates="video_draft", cascade="all, delete-orphan")
```

---

## `app/db/models/export.py`

```python
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Enum, ForeignKey, String, Text, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.enums import ExportStatus


class Export(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "exports"

    video_draft_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("video_drafts.id", ondelete="CASCADE"), index=True)
    status: Mapped[ExportStatus] = mapped_column(
        Enum(ExportStatus, name="export_status"),
        nullable=False,
        default=ExportStatus.queued,
        server_default=ExportStatus.queued.value,
        index=True,
    )

    export_video_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    export_subtitle_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    export_script_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    export_metadata_path: Mapped[str | None] = mapped_column(Text, nullable=True)

    export_preset: Mapped[str] = mapped_column(String(50), nullable=False, default="shorts_default", server_default="shorts_default")
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    video_draft = relationship("VideoDraft", back_populates="exports")
    jobs = relationship("Job", back_populates="export")
```

---

## `app/db/models/review_action.py`

```python
from __future__ import annotations

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ReviewAction(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "review_actions"

    video_draft_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("video_drafts.id", ondelete="CASCADE"), index=True)
    action_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    action_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False, default="operator", server_default="operator")

    video_draft = relationship("VideoDraft", back_populates="review_actions")
```

---

## `app/db/models/__init__.py`

Alembic autogenerate에서 중요하다.
Alembic은 `env.py`에서 `target_metadata`를 보고 변경 사항을 비교하므로, 모델 import 누락이 있으면 생성이 빠질 수 있다. ([alembic.sqlalchemy.org][2])

```python
from app.db.models.episode import Episode
from app.db.models.job import Job
from app.db.models.shot import Shot
from app.db.models.transcript_segment import TranscriptSegment
from app.db.models.candidate import Candidate
from app.db.models.script_draft import ScriptDraft
from app.db.models.video_draft import VideoDraft
from app.db.models.export import Export
from app.db.models.review_action import ReviewAction

__all__ = [
    "Episode",
    "Job",
    "Shot",
    "TranscriptSegment",
    "Candidate",
    "ScriptDraft",
    "VideoDraft",
    "Export",
    "ReviewAction",
]
```

---

# 5) Alembic 설정 초안

Alembic 문서 기준으로 `env.py`는 엔진/커넥션을 만들고, `target_metadata`를 연결해 migration context를 실행하는 역할이다. `revision --autogenerate`도 이 메타데이터를 기반으로 동작한다. ([alembic.sqlalchemy.org][3])

## `alembic/env.py`

```python
from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import get_settings
from app.db.base import Base
from app.db import models  # noqa: F401

config = context.config
settings = get_settings()

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        future=True,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

---

# 6) Alembic migration 파일 초안

autogenerate는 편하지만 완전 자동은 아니다. 특히 enum, 커스텀 타입, 렌더링 방식은 직접 검토가 필요하다는 점이 공식 문서에도 나와 있다. 그래서 아래처럼 **파일을 단계별로 쪼개는 방식**을 추천한다. ([alembic.sqlalchemy.org][2])

## `alembic/versions/001_create_enums.py`

```python
"""create enums

Revision ID: 001_create_enums
Revises:
Create Date: 2026-03-23 18:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "001_create_enums"
down_revision = None
branch_labels = None
depends_on = None


episode_status = postgresql.ENUM("uploaded", "processing", "ready", "failed", "archived", name="episode_status")
job_type = postgresql.ENUM("ingest", "transcode", "shot_detection", "transcript", "candidate_generation", "script_generation", "draft_render", "export_render", name="job_type")
job_status = postgresql.ENUM("queued", "running", "succeeded", "failed", "cancelled", name="job_status")
candidate_type = postgresql.ENUM("context_commentary", "nuance_translation", "psychology_analysis", name="candidate_type")
candidate_status = postgresql.ENUM("generated", "selected", "rejected", "drafted", "archived", name="candidate_status")
draft_status = postgresql.ENUM("created", "rendering", "ready", "failed", "approved", "rejected", name="draft_status")
export_status = postgresql.ENUM("queued", "rendering", "ready", "failed", name="export_status")
source_type = postgresql.ENUM("subtitle", "asr", "manual", name="source_type")
target_channel_type = postgresql.ENUM("kr_us_drama", "us_kr_drama", name="target_channel_type")
language_code = postgresql.ENUM("ko", "en", name="language_code")


def upgrade() -> None:
    bind = op.get_bind()
    episode_status.create(bind, checkfirst=True)
    job_type.create(bind, checkfirst=True)
    job_status.create(bind, checkfirst=True)
    candidate_type.create(bind, checkfirst=True)
    candidate_status.create(bind, checkfirst=True)
    draft_status.create(bind, checkfirst=True)
    export_status.create(bind, checkfirst=True)
    source_type.create(bind, checkfirst=True)
    target_channel_type.create(bind, checkfirst=True)
    language_code.create(bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    language_code.drop(bind, checkfirst=True)
    target_channel_type.drop(bind, checkfirst=True)
    source_type.drop(bind, checkfirst=True)
    export_status.drop(bind, checkfirst=True)
    draft_status.drop(bind, checkfirst=True)
    candidate_status.drop(bind, checkfirst=True)
    candidate_type.drop(bind, checkfirst=True)
    job_status.drop(bind, checkfirst=True)
    job_type.drop(bind, checkfirst=True)
    episode_status.drop(bind, checkfirst=True)
```

---

## `alembic/versions/002_create_episodes_jobs.py`

```python
"""create episodes and jobs

Revision ID: 002_create_episodes_jobs
Revises: 001_create_enums
Create Date: 2026-03-23 18:05:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "002_create_episodes_jobs"
down_revision = "001_create_enums"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "episodes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("show_title", sa.String(length=255), nullable=False),
        sa.Column("season_number", sa.Integer(), nullable=True),
        sa.Column("episode_number", sa.Integer(), nullable=True),
        sa.Column("episode_title", sa.String(length=255), nullable=True),
        sa.Column("original_language", sa.Enum("ko", "en", name="language_code", create_type=False), nullable=False),
        sa.Column("target_channel", sa.Enum("kr_us_drama", "us_kr_drama", name="target_channel_type", create_type=False), nullable=False),
        sa.Column("source_video_path", sa.Text(), nullable=False),
        sa.Column("proxy_video_path", sa.Text(), nullable=True),
        sa.Column("source_subtitle_path", sa.Text(), nullable=True),
        sa.Column("duration_seconds", sa.Numeric(10, 3), nullable=True),
        sa.Column("fps", sa.Numeric(8, 3), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=True),
        sa.Column("status", sa.Enum("uploaded", "processing", "ready", "failed", "archived", name="episode_status", create_type=False), nullable=False, server_default="uploaded"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_episodes_show_title", "episodes", ["show_title"])
    op.create_index("ix_episodes_status", "episodes", ["status"])

    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("episode_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("episodes.id", ondelete="CASCADE"), nullable=True),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("video_draft_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("export_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("celery_task_id", sa.String(length=255), nullable=True),
        sa.Column("type", sa.Enum("ingest", "transcode", "shot_detection", "transcript", "candidate_generation", "script_generation", "draft_render", "export_render", name="job_type", create_type=False), nullable=False),
        sa.Column("status", sa.Enum("queued", "running", "succeeded", "failed", "cancelled", name="job_status", create_type=False), nullable=False, server_default="queued"),
        sa.Column("progress_percent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("input_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("output_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_jobs_episode_id", "jobs", ["episode_id"])
    op.create_index("ix_jobs_type", "jobs", ["type"])
    op.create_index("ix_jobs_status", "jobs", ["status"])
    op.create_index("ix_jobs_celery_task_id", "jobs", ["celery_task_id"])


def downgrade() -> None:
    op.drop_index("ix_jobs_celery_task_id", table_name="jobs")
    op.drop_index("ix_jobs_status", table_name="jobs")
    op.drop_index("ix_jobs_type", table_name="jobs")
    op.drop_index("ix_jobs_episode_id", table_name="jobs")
    op.drop_table("jobs")

    op.drop_index("ix_episodes_status", table_name="episodes")
    op.drop_index("ix_episodes_show_title", table_name="episodes")
    op.drop_table("episodes")
```

---

## `alembic/versions/003_create_shots_transcripts.py`

```python
"""create shots and transcript segments"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "003_create_shots_transcripts"
down_revision = "002_create_episodes_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "shots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("episode_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("episodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("shot_index", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Numeric(10, 3), nullable=False),
        sa.Column("end_time", sa.Numeric(10, 3), nullable=False),
        sa.Column("thumbnail_path", sa.Text(), nullable=True),
        sa.Column("keyframe_path", sa.Text(), nullable=True),
        sa.Column("face_count", sa.Integer(), nullable=True),
        sa.Column("motion_score", sa.Numeric(6, 3), nullable=True),
        sa.Column("closeup_score", sa.Numeric(6, 3), nullable=True),
        sa.Column("emotion_intensity_score", sa.Numeric(6, 3), nullable=True),
        sa.Column("text_safe_area_score", sa.Numeric(6, 3), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("episode_id", "shot_index", name="uq_shots_episode_shot_index"),
    )
    op.create_index("ix_shots_episode_id", "shots", ["episode_id"])

    op.create_table(
        "transcript_segments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("episode_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("episodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("segment_index", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Numeric(10, 3), nullable=False),
        sa.Column("end_time", sa.Numeric(10, 3), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("normalized_text", sa.Text(), nullable=True),
        sa.Column("speaker_label", sa.String(length=100), nullable=True),
        sa.Column("source", sa.Enum("subtitle", "asr", "manual", name="source_type", create_type=False), nullable=False),
        sa.Column("confidence", sa.Numeric(6, 3), nullable=True),
        sa.Column("language", sa.Enum("ko", "en", name="language_code", create_type=False), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("episode_id", "segment_index", "source", name="uq_transcript_episode_segment_source"),
    )
    op.create_index("ix_transcript_episode_id", "transcript_segments", ["episode_id"])


def downgrade() -> None:
    op.drop_index("ix_transcript_episode_id", table_name="transcript_segments")
    op.drop_table("transcript_segments")
    op.drop_index("ix_shots_episode_id", table_name="shots")
    op.drop_table("shots")
```

---

## `alembic/versions/004_create_candidates.py`

```python
"""create candidates"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "004_create_candidates"
down_revision = "003_create_shots_transcripts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("episode_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("episodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("candidate_index", sa.Integer(), nullable=False),
        sa.Column("type", sa.Enum("context_commentary", "nuance_translation", "psychology_analysis", name="candidate_type", create_type=False), nullable=False),
        sa.Column("status", sa.Enum("generated", "selected", "rejected", "drafted", "archived", name="candidate_status", create_type=False), nullable=False, server_default="generated"),
        sa.Column("title_hint", sa.String(length=255), nullable=True),
        sa.Column("start_time", sa.Numeric(10, 3), nullable=False),
        sa.Column("end_time", sa.Numeric(10, 3), nullable=False),
        sa.Column("total_score", sa.Numeric(6, 3), nullable=False, server_default="0"),
        sa.Column("hook_score", sa.Numeric(6, 3), nullable=False, server_default="0"),
        sa.Column("clarity_score", sa.Numeric(6, 3), nullable=False, server_default="0"),
        sa.Column("tension_score", sa.Numeric(6, 3), nullable=False, server_default="0"),
        sa.Column("emotion_score", sa.Numeric(6, 3), nullable=False, server_default="0"),
        sa.Column("commentary_score", sa.Numeric(6, 3), nullable=False, server_default="0"),
        sa.Column("visual_score", sa.Numeric(6, 3), nullable=False, server_default="0"),
        sa.Column("source_dependence_penalty", sa.Numeric(6, 3), nullable=False, server_default="0"),
        sa.Column("repetition_penalty", sa.Numeric(6, 3), nullable=False, server_default="0"),
        sa.Column("risk_score", sa.Numeric(6, 3), nullable=False, server_default="0"),
        sa.Column("risk_level", sa.String(length=20), nullable=False, server_default="medium"),
        sa.Column("shot_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("transcript_segment_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("episode_id", "candidate_index", name="uq_candidates_episode_candidate_index"),
    )
    op.create_index("ix_candidates_episode_id", "candidates", ["episode_id"])
    op.create_index("ix_candidates_status", "candidates", ["status"])
    op.create_index("ix_candidates_type", "candidates", ["type"])
    op.create_index("ix_candidates_risk_level", "candidates", ["risk_level"])


def downgrade() -> None:
    op.drop_index("ix_candidates_risk_level", table_name="candidates")
    op.drop_index("ix_candidates_type", table_name="candidates")
    op.drop_index("ix_candidates_status", table_name="candidates")
    op.drop_index("ix_candidates_episode_id", table_name="candidates")
    op.drop_table("candidates")
```

---

## `alembic/versions/005_create_script_drafts_video_drafts_exports.py`

```python
"""create drafts and exports"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "005_create_script_drafts_video_drafts_exports"
down_revision = "004_create_candidates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "script_drafts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("language", sa.Enum("ko", "en", name="language_code", create_type=False), nullable=False),
        sa.Column("hook_text", sa.Text(), nullable=False),
        sa.Column("intro_text", sa.Text(), nullable=True),
        sa.Column("body_text", sa.Text(), nullable=False),
        sa.Column("outro_text", sa.Text(), nullable=True),
        sa.Column("cta_text", sa.Text(), nullable=True),
        sa.Column("full_script_text", sa.Text(), nullable=False),
        sa.Column("estimated_duration_seconds", sa.Numeric(10, 3), nullable=True),
        sa.Column("title_options", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("hook_options", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("cta_options", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("commentary_density_score", sa.Numeric(6, 3), nullable=False, server_default="0"),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("is_selected", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("candidate_id", "version_no", name="uq_script_drafts_candidate_version"),
    )
    op.create_index("ix_script_drafts_candidate_id", "script_drafts", ["candidate_id"])

    op.create_table(
        "video_drafts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("script_draft_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("script_drafts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.Enum("created", "rendering", "ready", "failed", "approved", "rejected", name="draft_status", create_type=False), nullable=False, server_default="created"),
        sa.Column("template_type", sa.String(length=50), nullable=False),
        sa.Column("tts_voice_key", sa.String(length=100), nullable=True),
        sa.Column("aspect_ratio", sa.String(length=20), nullable=False, server_default="9:16"),
        sa.Column("width", sa.Integer(), nullable=False, server_default="1080"),
        sa.Column("height", sa.Integer(), nullable=False, server_default="1920"),
        sa.Column("draft_video_path", sa.Text(), nullable=True),
        sa.Column("subtitle_path", sa.Text(), nullable=True),
        sa.Column("waveform_path", sa.Text(), nullable=True),
        sa.Column("thumbnail_path", sa.Text(), nullable=True),
        sa.Column("burned_caption", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("render_config", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("timeline_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("operator_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("candidate_id", "version_no", name="uq_video_drafts_candidate_version"),
    )
    op.create_index("ix_video_drafts_candidate_id", "video_drafts", ["candidate_id"])
    op.create_index("ix_video_drafts_script_draft_id", "video_drafts", ["script_draft_id"])
    op.create_index("ix_video_drafts_status", "video_drafts", ["status"])

    op.create_table(
        "exports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("video_draft_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("video_drafts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.Enum("queued", "rendering", "ready", "failed", name="export_status", create_type=False), nullable=False, server_default="queued"),
        sa.Column("export_video_path", sa.Text(), nullable=True),
        sa.Column("export_subtitle_path", sa.Text(), nullable=True),
        sa.Column("export_script_path", sa.Text(), nullable=True),
        sa.Column("export_metadata_path", sa.Text(), nullable=True),
        sa.Column("export_preset", sa.String(length=50), nullable=False, server_default="shorts_default"),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_exports_video_draft_id", "exports", ["video_draft_id"])
    op.create_index("ix_exports_status", "exports", ["status"])


def downgrade() -> None:
    op.drop_index("ix_exports_status", table_name="exports")
    op.drop_index("ix_exports_video_draft_id", table_name="exports")
    op.drop_table("exports")

    op.drop_index("ix_video_drafts_status", table_name="video_drafts")
    op.drop_index("ix_video_drafts_script_draft_id", table_name="video_drafts")
    op.drop_index("ix_video_drafts_candidate_id", table_name="video_drafts")
    op.drop_table("video_drafts")

    op.drop_index("ix_script_drafts_candidate_id", table_name="script_drafts")
    op.drop_table("script_drafts")
```

---

## `alembic/versions/006_create_review_actions_and_indexes.py`

```python
"""create review actions and job fks"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "006_create_review_actions_and_indexes"
down_revision = "005_create_script_drafts_video_drafts_exports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "review_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("video_draft_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("video_drafts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("action_type", sa.String(length=50), nullable=False),
        sa.Column("action_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=100), nullable=False, server_default="operator"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_review_actions_video_draft_id", "review_actions", ["video_draft_id"])
    op.create_index("ix_review_actions_action_type", "review_actions", ["action_type"])

    op.create_foreign_key("fk_jobs_candidate", "jobs", "candidates", ["candidate_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("fk_jobs_video_draft", "jobs", "video_drafts", ["video_draft_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("fk_jobs_export", "jobs", "exports", ["export_id"], ["id"], ondelete="CASCADE")


def downgrade() -> None:
    op.drop_constraint("fk_jobs_export", "jobs", type_="foreignkey")
    op.drop_constraint("fk_jobs_video_draft", "jobs", type_="foreignkey")
    op.drop_constraint("fk_jobs_candidate", "jobs", type_="foreignkey")

    op.drop_index("ix_review_actions_action_type", table_name="review_actions")
    op.drop_index("ix_review_actions_video_draft_id", table_name="review_actions")
    op.drop_table("review_actions")
```

---

# 7) FastAPI용 Pydantic 스키마 초안

## `app/schemas/common.py`

```python
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class TimestampOut(ORMModel):
    created_at: datetime
    updated_at: datetime
```

---

## `app/schemas/episode.py`

```python
from uuid import UUID
from pydantic import BaseModel

from app.schemas.common import TimestampOut


class EpisodeCreate(BaseModel):
    show_title: str
    season_number: int | None = None
    episode_number: int | None = None
    episode_title: str | None = None
    original_language: str
    target_channel: str


class EpisodeOut(TimestampOut):
    id: UUID
    show_title: str
    season_number: int | None = None
    episode_number: int | None = None
    episode_title: str | None = None
    original_language: str
    target_channel: str
    status: str
    duration_seconds: float | None = None
    fps: float | None = None
    width: int | None = None
    height: int | None = None
```

---

## `app/schemas/candidate.py`

```python
from uuid import UUID
from pydantic import BaseModel

from app.schemas.common import TimestampOut


class CandidateScoreOut(BaseModel):
    total_score: float
    hook_score: float
    clarity_score: float
    tension_score: float
    emotion_score: float
    commentary_score: float
    visual_score: float


class CandidateOut(TimestampOut):
    id: UUID
    episode_id: UUID
    type: str
    status: str
    title_hint: str | None = None
    start_time: float
    end_time: float
    total_score: float
    risk_score: float
    risk_level: str
```

---

# 8) 엔드포인트 핸들러 최소 구현 예시

## `app/api/v1/episodes.py`

```python
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.db.models.episode import Episode
from app.schemas.episode import EpisodeOut

router = APIRouter()


@router.post("", response_model=EpisodeOut, status_code=status.HTTP_201_CREATED)
def create_episode(
    show_title: str = Form(...),
    season_number: int | None = Form(None),
    episode_number: int | None = Form(None),
    episode_title: str | None = Form(None),
    original_language: str = Form(...),
    target_channel: str = Form(...),
    video_file: UploadFile = File(...),
    subtitle_file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    # 실제 구현에서는 storage_service로 파일 저장
    episode = Episode(
        show_title=show_title,
        season_number=season_number,
        episode_number=episode_number,
        episode_title=episode_title,
        original_language=original_language,
        target_channel=target_channel,
        source_video_path=f"/tmp/{video_file.filename}",
        source_subtitle_path=f"/tmp/{subtitle_file.filename}" if subtitle_file else None,
    )
    db.add(episode)
    db.commit()
    db.refresh(episode)
    return episode


@router.get("/{episode_id}", response_model=EpisodeOut)
def get_episode(episode_id: UUID, db: Session = Depends(get_db)):
    episode = db.get(Episode, episode_id)
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")
    return episode
```

---

## `app/api/v1/candidates.py`

```python
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.db.models.candidate import Candidate
from app.schemas.candidate import CandidateOut

router = APIRouter()


@router.get("/{candidate_id}", response_model=CandidateOut)
def get_candidate(candidate_id: UUID, db: Session = Depends(get_db)):
    candidate = db.get(Candidate, candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return candidate
```

---

# 9) Celery 앱 최소 초안

## `app/core/celery_app.py`

```python
from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "drama_shorts_copilot",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.task_routes = {
    "app.tasks.ingest_tasks.*": {"queue": "io_queue"},
    "app.tasks.analysis_tasks.*": {"queue": "cpu_queue"},
    "app.tasks.render_tasks.*": {"queue": "gpu_or_heavy_queue"},
}
```

---

## `app/tasks/analysis_tasks.py`

```python
from app.core.celery_app import celery_app


@celery_app.task(name="app.tasks.analysis_tasks.detect_shots")
def detect_shots(episode_id: str) -> dict:
    # TODO: PySceneDetect / ffmpeg 기반 샷 분할
    return {"episode_id": episode_id, "shot_count": 0}


@celery_app.task(name="app.tasks.analysis_tasks.generate_candidates")
def generate_candidates(episode_id: str) -> dict:
    # TODO: transcript + shot + signal 기반 후보 생성
    return {"episode_id": episode_id, "candidate_count": 0}
```

---

# 10) 실행 순서

## 패키지 설치 예시

```bash
pip install fastapi uvicorn sqlalchemy psycopg2-binary alembic pydantic-settings celery redis python-multipart
```

## Alembic 초기화 후 적용

```bash
alembic upgrade head
```

## 서버 실행

```bash
uvicorn app.main:app --reload
```

## Celery 워커 실행

```bash
celery -A app.core.celery_app.celery_app worker -Q io_queue,cpu_queue,gpu_or_heavy_queue --loglevel=info
```

---

# 11) 지금 단계에서 가장 중요한 체크포인트

1. **모델 import 누락 없이 `Base.metadata`에 전부 등록**
2. **Enum 이름을 migration과 모델에서 동일하게 유지**
3. **`metadata` 컬럼명은 SQLAlchemy 내부 `metadata`와 헷갈리니 모델 속성명은 `metadata_json`으로 둔 것 유지**
4. **Job FK 일부는 순환 참조 문제 때문에 마지막 migration에서 붙이는 방식 유지**
5. **autogenerate만 맹신하지 말고 enum/server_default/index는 항상 수동 검토**

Alembic autogenerate는 편하지만, 공식 문서도 모든 변경을 전부 완벽하게 감지하는 도구로 설명하지는 않는다. 수동 검토 전제는 반드시 두는 게 맞다. ([alembic.sqlalchemy.org][2])

---

# 12) 다음으로 바로 붙이면 좋은 것

이제 실제 구현 단계에서는 아래 3개가 다음 우선순위다.

* **`storage_service.py`**: 로컬/S3 저장 추상화
* **`analysis_service.py`**: shot/transcript/candidate 생성 로직
* **`render_service.py`**: timeline_json → ffmpeg 명령 생성

다음 답변에서 원하면
**`storage_service.py`, `analysis_service.py`, `render_service.py`의 실제 코드 초안**까지 바로 이어서 적어주겠다.

[1]: https://docs.sqlalchemy.org/en/latest/orm/declarative_tables.html?utm_source=chatgpt.com "Table Configuration with Declarative — SQLAlchemy 2.1 ..."
[2]: https://alembic.sqlalchemy.org/en/latest/autogenerate.html?utm_source=chatgpt.com "Auto Generating Migrations - Alembic's documentation!"
[3]: https://alembic.sqlalchemy.org/en/latest/tutorial.html?utm_source=chatgpt.com "Tutorial — Alembic 1.18.4 documentation"
