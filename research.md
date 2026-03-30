# Shorten 프로젝트 심층 분석 보고서

## 목차

1. [프로젝트 개요](#1-프로젝트-개요)
2. [전체 아키텍처](#2-전체-아키텍처)
3. [데이터베이스 스키마](#3-데이터베이스-스키마)
4. [설정 및 환경변수](#4-설정-및-환경변수)
5. [분석 파이프라인 (Celery 태스크)](#5-분석-파이프라인-celery-태스크)
6. [분석 서비스 상세](#6-분석-서비스-상세)
7. [후보 생성 알고리즘](#7-후보-생성-알고리즘)
8. [스코어링 공식 전체](#8-스코어링-공식-전체)
9. [콘텐츠 생성 서비스](#9-콘텐츠-생성-서비스)
10. [API 엔드포인트 전체](#10-api-엔드포인트-전체)
11. [프론트엔드 구조](#11-프론트엔드-구조)
12. [스모크 테스트](#12-스모크-테스트)
13. [스토리지 레이아웃](#13-스토리지-레이아웃)
14. [메타데이터 JSON 구조](#14-메타데이터-json-구조)
15. [한계 및 미구현 사항](#15-한계-및-미구현-사항)

---

## 1. 프로젝트 개요

**Shorten**은 장편 드라마 에피소드를 분석하여 쇼츠(9:16 세로형) 후보 클립을 자동 생성하는 로컬-퍼스트 MVP입니다.

### 핵심 목표
- 에피소드 영상을 업로드하면 쇼츠 후보를 자동으로 발굴
- 대사 구조, 시각적 임팩트, 오디오 에너지 등 다중 시그널로 후보 스코어링
- 선택된 후보에 대해 스크립트 초안 → 비디오 초안 → 내보내기 워크플로우 지원
- AWS 등 외부 클라우드 없이 단일 머신에서 동작

### 기술 스택

| 계층 | 기술 |
|------|------|
| Backend | FastAPI, SQLAlchemy 2.0, Alembic, Celery 5, Redis |
| Frontend | Next.js 16 (App Router), React 19, TanStack Query |
| DB | PostgreSQL (프로덕션) / SQLite (로컬 개발·테스트) |
| 미디어 처리 | FFmpeg/FFprobe CLI |
| LLM | OpenAI SDK (mock fallback 지원) |
| 언어 | Python 3.11+, TypeScript |

---

## 2. 전체 아키텍처

```
[브라우저: Next.js 16]
  ↕ REST API (http://localhost:8000/api/v1)
[FastAPI 서버]
  ↕ SQLAlchemy 2.0
[PostgreSQL / SQLite]
  ↕ Celery (Redis 브로커)
[Celery Worker]
  ↕ FFmpeg, OpenAI API
[로컬 디스크 storage/]
```

### 전체 데이터 흐름

```
에피소드 업로드
  └→ ingest (ffprobe 메타데이터)
       └→ transcode_proxy (480p, 6fps 프록시 생성)
            └→ detect_shots (FFmpeg scene 필터)
                 └→ extract_keyframes (Vision 스캔용 프레임 추출)
                      └→ extract_transcript (SRT/WebVTT 파싱)
                           └→ compute_signals (speech ratio, cut density 등)
                                └→ generate_candidates (다중 트랙 스코어링)
                                     └→ [Optional] vision_rerank (GPT-4 Vision)
                                          └→ Candidate DB 저장

각 후보에 대해:
  └→ ScriptDraft 생성 (OpenAI 또는 Mock)
       └→ VideoDraft 생성 (FFmpeg 템플릿 렌더링, TTS 포함)
            └→ ShortClip 렌더링 (FFmpeg 9:16 실제 동작)
                 └→ Export 패키징 (MP4 + SRT + 스크립트 + 메타데이터)
```

---

## 3. 데이터베이스 스키마

**파일:** `backend/app/db/models.py`

### Episode

에피소드 원본 영상 및 분석 상태를 저장하는 핵심 엔티티.

```
id                  UUID (PK)
show_title          str
season_number       int? (nullable)
episode_number      int? (nullable)
episode_title       str? (nullable)
original_language   str (기본 "en")
target_channel      str (기본 "kr_us_drama")
status              Enum: UPLOADED | PROCESSING | READY | FAILED
source_video_path   str (원본 영상 경로)
source_subtitle_path str? (업로드된 SRT 경로)
proxy_video_path    str? (프록시 영상 경로, 분석 후 생성)
audio_path          str? (분리 오디오 경로)
duration_seconds    float? (ffprobe로 추출)
fps                 float?
width               int?
height              int?
metadata_json       JSON (분석 전 과정의 캐시·결과 저장, 구조는 14절 참조)
created_at, updated_at
Relations: jobs, shots, transcript_segments, candidates (all cascade delete)
```

### Shot

FFmpeg scene detection으로 감지된 샷 경계.

```
id              UUID (PK)
episode_id      FK → Episode
shot_index      int (1-based)
start_time      float (초)
end_time        float (초)
thumbnail_path  str? (JPEG 썸네일 경로)
```

### TranscriptSegment

파싱된 자막 큐. 현재 speaker_label은 미사용.

```
id              UUID (PK)
episode_id      FK → Episode
segment_index   int (1-based)
start_time      float
end_time        float
text            str
speaker_label   str? (미사용)
```

### Candidate

쇼츠 후보 클립. 프로젝트의 핵심 엔티티.

```
id               UUID (PK)
episode_id       FK → Episode
candidate_index  int (순위)
type             str (기본 "context_commentary")
status           Enum: GENERATED | SELECTED | REJECTED | DRAFTED
title_hint       str (UI 표시용 제목)
start_time       float
end_time         float
duration_seconds float (clip_spans 합산)
total_score      float (0–10 정규화)
risk_score       float
risk_level       str ("low" | "medium" | "high")
scores_json      JSON (17개 이상 컴포넌트 점수)
risk_reasons     list[str] (경고 메시지)
metadata_json    JSON (clip_spans, transcript_excerpt, entities, arc 정보 등)
selected         bool
short_clip_path  str? (렌더링된 쇼츠 경로)
Relations: script_drafts, jobs, video_drafts
```

### ScriptDraft

OpenAI(또는 Mock)로 생성된 스크립트 초안. 버전 관리됨.

```
id                          UUID (PK)
candidate_id                FK → Candidate
version_no                  int
language                    str ("ko" | "en")
hook_text                   str
body_text                   str
cta_text                    str
full_script_text            str (hook + body + cta 연결)
estimated_duration_seconds  float (len(text) / 12)
title_options               list[str] (제목 후보 3개 이상)
metadata_json               JSON (provider, model, fallback_reason 등)
is_selected                 bool
Relations: candidate, video_drafts
```

### VideoDraft

렌더링 가능한 비디오 초안. `video_template_renderer.py`로 실제 FFmpeg 렌더링.

```
id                UUID (PK)
candidate_id      FK → Candidate
script_draft_id   FK → ScriptDraft
version_no        int
status            Enum: CREATED | QUEUED | RUNNING | READY | FAILED | APPROVED | REJECTED
template_type     str (기본 "context_commentary_v1")
tts_voice_key     str?
aspect_ratio      str (기본 "9:16")
width, height     int (기본 1080×1920)
draft_video_path  str?
subtitle_path     str?
waveform_path     str?
thumbnail_path    str?
burned_caption    bool
render_config_json JSON (FFmpeg/template 파라미터)
timeline_json     JSON (클립·효과·TTS 타이밍 시퀀스)
metadata_json     JSON (render_revision, operator_notes 등)
Relations: candidate, script_draft, exports (cascade)
```

### Export

최종 배포용 패키지.

```
id                    UUID (PK)
video_draft_id        FK → VideoDraft
status                Enum: QUEUED | RUNNING | READY | FAILED
export_video_path     str?
export_subtitle_path  str?
export_script_path    str?
export_metadata_path  str?
export_preset         str ("shorts_default" | "review_lowres" | "archive_master")
file_size_bytes       int?
metadata_json         JSON (include_srt, include_script_txt 등)
```

### Job

Celery 비동기 작업 추적.

```
id               UUID (PK)
episode_id       FK → Episode (nullable)
candidate_id     FK → Candidate (nullable)
type             Enum: ANALYSIS | SCRIPT_GENERATION | VIDEO_DRAFT_RENDER | EXPORT_RENDER | SHORT_CLIP_RENDER
status           Enum: QUEUED | RUNNING | SUCCEEDED | FAILED | CANCELLED
progress_percent int (0–100)
current_step     str (현재 실행 중인 단계명)
error_message    str?
payload_json     JSON (입출력 데이터)
created_at, updated_at
```

### 마이그레이션 이력

| 버전 | 내용 |
|------|------|
| 0001_initial_schema | Episode, Shot, TranscriptSegment, Candidate, ScriptDraft, Job |
| 0002_video_drafts_exports | VideoDraft, Export 모델 + 상태 Enum |
| 0003_candidate_short_clip | Candidate에 short_clip_path 컬럼 추가 |
| 0004_video_draft_metadata | metadata_json 컬럼 확장 (렌더 추적) |

---

## 4. 설정 및 환경변수

**파일:** `backend/app/core/config.py`, `backend/.env.example`

### 핵심 설정값 (Pydantic Settings)

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `DATABASE_URL` | `sqlite:///data/app.db` | PostgreSQL 또는 SQLite |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis URL |
| `CELERY_BROKER_URL` | `memory://` | Celery 브로커 |
| `CELERY_RESULT_BACKEND` | `cache+memory://` | Celery 결과 백엔드 |
| `CELERY_TASK_ALWAYS_EAGER` | `True` | True = 동기 실행 (테스트용) |
| `OPENAI_API_KEY` | `""` | 없으면 Mock 폴백 |
| `OPENAI_MODEL` | `"gpt-4.1"` | 스크립트 생성 모델 |
| `ALLOW_MOCK_LLM_FALLBACK` | `True` | OpenAI 실패 시 결정적 Mock |
| `VISION_CANDIDATE_RERANK` | `True` | GPT-4 Vision 재랭크 활성화 |
| `VISION_MAX_CANDIDATES_PER_EPISODE` | `8` | Vision 적용 최대 후보 수 |
| `VISION_MAX_FRAMES_PER_CANDIDATE` | `6` | 후보당 최대 프레임 수 |
| `VISION_IMAGE_MAX_WIDTH` | `640` | Vision 입력 이미지 최대 너비 |
| `VISION_MODEL` | `"gpt-4.1"` | Vision 재랭크 모델 |
| `VISION_PROMPT_VERSION` | `"vision_candidate_rerank_v1"` | 프롬프트 버전 |
| `FFMPEG_SCENE_THRESHOLD` | `0.32` | FFmpeg scene 감지 임계값 (낮을수록 더 많은 컷 감지) |
| `PROXY_MAX_WIDTH` | `480` | 프록시 영상 최대 너비 |
| `PROXY_VIDEO_FPS` | `6` | 프록시 FPS |
| `PROXY_VIDEO_CRF` | `31` | 프록시 화질 (높을수록 저화질) |
| `PROXY_AUDIO_BITRATE_KBPS` | `64` | 오디오 비트레이트 |
| `STORAGE_ROOT` | `"./storage"` | 로컬 파일 저장 루트 |
| `CORS_ALLOWED_ORIGINS` | `"http://localhost:3000,..."` | CORS 허용 오리진 |

### 설정 효과 비교

| 설정 | 개발(smoke) | Docker 로컬 프로덕션 |
|------|-------------|----------------------|
| DB | SQLite | PostgreSQL 17 |
| Celery | eager (동기) | Redis + 비동기 Worker |
| OpenAI | Mock fallback | 실제 API (키 있을 시) |
| Vision | 비활성 | 활성 가능 |
| Storage | `storage/smoke/` | `storage/` 마운트 볼륨 |

---

## 5. 분석 파이프라인 (Celery 태스크)

**파일:** `backend/app/tasks/pipelines.py`

### 태스크 체인 구조

```python
launch_analysis_pipeline(episode_id, job_id)
  → Celery chain:
      ingest_episode.s()
        → transcode_proxy.s()
          → detect_shots.s()
            → extract_keyframes.s()
              → extract_or_generate_transcript.s()
                → compute_signals.s()
                  → generate_candidates.s()
```

### 각 태스크의 공통 패턴

```python
@celery_app.task
def some_step(context_dict):
    db = get_session()
    job = db.get(Job, job_id)
    job.status = RUNNING
    job.current_step = "step_name"

    result = do_work()

    job.status = SUCCEEDED
    job.progress_percent = N
    db.commit()

    return {**context_dict, "new_key": result}
```

### 별도 태스크 체인

| 체인 | 진입점 |
|------|--------|
| 스크립트 생성 | `generate_script_drafts_task` |
| 쇼츠 클립 렌더링 | `render_short_clip_task` |
| 비디오 초안 렌더링 | `render_video_draft_task` |
| 내보내기 렌더링 | `render_export_task` |

---

## 6. 분석 서비스 상세

### 6.1 Ingest Episode (`analysis_service.py`)

- `ffprobe -show_format -show_streams` 실행
- 결과: duration, fps, width, height, has_audio 저장
- Episode 레코드의 duration_seconds, fps, width, height 업데이트
- 실패 시 기본값(duration=60, fps=25, width=1920, height=1080) 사용
- `metadata_json["media_probe"]` = `{status, duration_seconds, fps, width, height}`

### 6.2 Proxy Transcoding (`proxy_transcoding.py`)

```bash
# 실행되는 FFmpeg 명령 (의사 코드)
ffmpeg -i source.mp4 \
  -vf "scale='min(iw,480)':-2" \
  -r 6 \
  -crf 31 \
  -preset veryfast \
  -an \
  proxy/analysis_proxy.mp4

ffmpeg -i source.mp4 \
  -vn -acodec aac -ab 64k \
  audio/analysis_audio.m4a
```

- **캐싱:** 소스 파일 서명(크기+mtime) + 프로파일 버전으로 캐시 키 생성
- **폴백:** 프록시 생성 실패 시 원본 소스 경로 반환
- `metadata_json["proxy_transcode"]` = `{version, status, mode}`

### 6.3 Shot Detection (`shot_detection.py`)

```bash
# FFmpeg scene 감지
ffmpeg -i proxy.mp4 \
  -vf "select=gt(scene\,0.32),showinfo" \
  -f null -
```

- 출력에서 타임스탬프 파싱
- **병합:** 0.28초 미만 간격의 샷 병합
- **상한:** 최대 100개 샷 (MAX_SHOTS)
- **썸네일:** 각 샷 시작 시각에서 JPEG 추출; 실패 시 placeholder
- **폴백:** 감지 실패 시 에피소드를 균등 분할하여 가상 샷 생성
- `metadata_json["shot_detection"]` = `{mode, status, shot_count, intervals, cache_key}`

### 6.4 Keyframe Extraction (`keyframe_extraction.py`)

- 각 샷에서 6개 프레임을 균등 간격으로 추출 (1 FPS로 프록시에서 샘플링)
- 저장 경로: `shots/{shot_index:04d}/frame_{frame_num:03d}.jpg`
- Vision 스캔 활성화 시: 프레임을 base64로 인코딩 → GPT-4 Vision에 전달하여 장면 분석
- `metadata_json["vision_scan"]` = `{status, frame_count, shots_with_keyframes, version}`

### 6.5 Transcript Parsing (`subtitle_parse.py`)

- 업로드된 SRT / WebVTT 파일만 지원 (ASR 없음)
- SRT 큐 파싱: `-->` 기준으로 시작/종료 시각 + 텍스트 추출
- WebVTT도 동일 포맷
- TranscriptSegment 레코드 생성 (1-indexed segment_index)
- `metadata_json["transcript_source"]` = `"uploaded_subtitle"` | `"parse_failed"` | `"none"`

### 6.6 Signal Computation (`analysis_service.py`)

```python
signals = {
  "algorithm": "signals_v1",
  "transcript_segment_count": len(segments),
  "shot_count": len(shots),
  "total_chars": sum(len(s.text) for s in segments),
  "median_cue_duration": statistics.median([s.end - s.start for s in segments]),
  "estimated_speech_timeline_ratio": total_speech_time / episode_duration,
  "commentary_friendly": speech_ratio > 0.12 and seg_count >= 3
}
```

이 시그널은 UI 표시용 및 하위 후보 생성 휴리스틱에서 참조됨.

---

## 7. 후보 생성 알고리즘

**파일:** `backend/app/services/candidate_generation.py` 및 관련 모듈

### 7.1 세 가지 트랙

후보 생성은 세 트랙에서 독립적으로 씨앗(Seed)을 생성한 후 통합 스코어링을 거칩니다.

```
트랙 A: Dialogue-Driven (대화 구조 기반)
  └→ 자막 큐 → micro-event 분할 → 윈도우 열거 → 스코어링

트랙 B: Visual-Impact (시각 임팩트 기반)
  └→ 샷 패턴 분석 → 컷 밀도 스파이크 · 반응샷 패턴 감지

트랙 C: Audio-Reaction (오디오 에너지 기반)
  └→ 오디오 에너지 분석 → FFmpeg astats RMS 기반 동적 구간 탐지 (실제 구현)
```

### 7.2 Micro-Event 생성

대사 자막 큐들을 의미 단위로 묶은 "micro-event"로 분할.

**경계 조건 (`_is_boundary`):**
```python
- 누적 duration >= 18.0초
- gap_to_next >= 1.8초 AND current_duration >= 4.0초
- "?", "!", "?!", "!?"로 끝나고 duration >= 4.0초
- reaction_signal이 임계값 이상
- payoff_signal이 임계값 이상
```

각 micro-event는 다음을 포함:
```python
CandidateEvent(
  start_time, end_time,
  text,          # 병합된 자막 텍스트
  event_kind,    # "question" | "reaction" | "payoff" | "neutral"
  tone_signals,  # 아래 6.7절 참조
  setup_score, escalation_score, reaction_score, payoff_score,
  standalone_score, context_dependency_score,
  visual_impact_score, audio_impact_score
)
```

### 7.3 윈도우 열거 (`_enumerate_windows`)

- micro-event 슬라이스: 최대 10개 이벤트
- 윈도우 길이: 30–180초 (MIN_WINDOW_SEC ~ MAX_WINDOW_SEC)
- 슬라이딩 방식: 시작 이벤트를 1씩 이동하며 가능한 모든 종료점 탐색
- 자막이 없으면 샷 경계를 대신 사용하여 씨앗 생성

### 7.4 언어 시그널 감지 (`candidate_language_signals.py`)

키워드 기반으로 영어·한국어 텍스트에서 6가지 tone signal 추출:

```python
def tone_signals(text: str) -> dict:
  normalized = text.lower().strip()

  question_signal = 끝이 "?" 또는 "?" 포함 키워드 존재 여부
  reaction_signal = ["omg", "no way", "seriously", "seriously?",
                     "진짜", "말도 안 돼", "헐", "어떻게"] 등 키워드 빈도
  payoff_signal  = ["so that's why", "turns out", "finally",
                     "결국", "그래서", "드디어"] 등
  emotion_signal = ["sorry", "love", "miss", "hurt",
                     "감동", "눈물", "울", "사랑"] 등
  comedy_signal  = ["funny", "hilarious", "ridiculous",
                     "웃", "웃기", "농담", "유머"] 등
  tension_signal = ["stop", "wait", "don't",
                     "멈춰", "안 돼", "왜", "위험"] 등
  surprise_signal = ["what?!", "how is this",
                      "세상에", "말이 돼?", "충격"] 등

  # 각 signal: 빈도 * 0.2, min(1.0, value) 로 정규화
  return {question, reaction, payoff, emotion, comedy, tension, surprise}
```

### 7.5 시각 시그널 (`candidate_visual_signals.py`)

샷 배열에서 다음 패턴을 감지하여 Visual 씨앗 생성:

- **컷 밀도 스파이크:** 로컬 컷 빈도가 에피소드 평균 대비 1.5배 이상인 구간
- **반응샷 패턴:** 3개 이상 연속으로 2초 미만 샷 (CUT-CUT-CUT 패턴)
- **저대사·고시각 구간:** speech_coverage < 0.3 AND cut_density > 평균

### 7.6 오디오 시그널 (`candidate_audio_signals.py`)

- **현재 구현 (실제 동작):** FFmpeg `astats` 필터로 5초 세그먼트 RMS 측정 → 무음→스파이크, 에너지 버스트, 볼륨 점프 3가지 시그널 합산 → `audio_impact_score` 계산
- `generate_audio_seeds()`: 에피소드 프록시에서 최대 10개 오디오 씨앗 생성
- **미구현:** 고급 spectral 분석, 화자 분리, 음악 vs. 대사 구분

### 7.7 스코어링 (`score_window`)

17개 이상 컴포넌트로 구성 → 아래 8절에서 상세 설명.

### 7.8 중복 제거 (NMS, `dedupe_scored_windows`)

```python
1. total_score 내림차순 정렬
2. 각 윈도우에 대해:
   a. IOU(시간 겹침) >= 0.52 이면 → 제거 (중복)
   b. Jaccard(텍스트 유사도) >= 0.82 AND 시간 근접 → 제거
   c. 통과한 경우 kept_list에 추가
3. 최대 MAX_CANDIDATES=14개 반환
```

**IOU 공식:**
```
overlap = min(end_a, end_b) - max(start_a, start_b)
union   = max(end_a, end_b) - min(start_a, start_b)
iou     = overlap / union
```

### 7.9 복합 후보 생성 (`composite_candidate_generation.py`)

비연속 세그먼트들을 이어 붙인 복합 후보를 빔 서치로 생성.

**빔 서치 (`beam_search_arcs`):**
```python
for each seed_window as start_node:
  beam = [ChainState(windows=[seed_window], score=seed_window.score)]
  for step in range(MAX_COMPOSITE_SEGMENTS-1):
    for each state in beam:
      for each candidate_extension in episode_windows:
        if 6s <= gap <= 420s:         # 유효한 간격
          if total_duration <= 64s:   # 최대 합산 길이
            adjacency = compute_adjacency(last_window, extension):
              # entity 겹침 * 0.4
              # + QA 매칭 * 0.35
              # + reaction 연속성 * 0.25
            new_state = extend(state, extension, adjacency)
            beam.append(new_state)
    beam = top_k(beam, k=BEAM_WIDTH=4)
  best_chains.extend(beam)

return top_N(best_chains, N=10)
```

각 복합 후보의 `clip_spans` (arc beam search 결과 예시):
```json
[
  {"start_time": 115.0, "end_time": 120.0, "order": 0, "role": "support_pre"},
  {"start_time": 120.0, "end_time": 145.0, "order": 1, "role": "core_setup"},
  {"start_time": 200.0, "end_time": 220.0, "order": 2, "role": "core_payoff"},
  {"start_time": 220.0, "end_time": 224.0, "order": 3, "role": "support_post"}
]
```

역할 분류 (`candidate_spans.py` 기준):
- **CORE_ROLES:** `core_setup` | `core_escalation` | `core_payoff` | `core_reaction` | `core_dialogue` | `core_followup` | `main` | `setup` | `payoff` | `reaction` | `followup` | `dialogue`
- **SUPPORT_ROLES:** `support_pre` | `support_post` | `support_bridge`

### 7.10 Vision 재랭크 (`vision_candidate_refinement.py`)

`VISION_CANDIDATE_RERANK=True`일 때 상위 8개 후보에 적용.

```python
for candidate in top_8_candidates:
  frames = extract_up_to_6_keyframes(candidate)
  response = openai.chat.completions.create(
    model="gpt-4.1",
    messages=[
      system: "You evaluate short-form video candidates for social media.",
      user: [
        *[{type: "image_url", url: f"data:image/jpeg;base64,{frame}"} for frame in frames],
        {type: "text", text: build_prompt(candidate, transcript_excerpt, scores)}
      ]
    ],
    response_format={"type": "json_object"}
  )
  # 기대 응답: {"watchability": 0-10, "standalone_clarity": 0-10, "comment_potential": 0-10, "reason": "..."}
  vision_score = (watchability + standalone_clarity + comment_potential) / 3
  delta = (vision_score - 5.0) / 5.0 * 1.5  # → [-1.5, +1.5]
  candidate.total_score += delta

  # 결과 캐싱: metadata_json["vision_rerank_cache"][hash(frames + prompt_version)]
```

### 7.11 Arc 기반 재랭크 (`candidate_rerank.py`)

모든 후보에 적용되는 휴리스틱 재랭크.

```python
arc_quality = (
  setup_strength          * 0.15  # 설정부 강도 (첫 이벤트)
  + payoff_strength       * 0.25  # 페이오프 강도 (마지막 이벤트)
  + setup_to_payoff_delta * 0.15  # 서사 상승폭
  + arc_continuity        * 0.10  # 엔티티 일관성
  + standalone            * 0.15  # 독립 이해도
  + visual_audio_impact   * 0.05  # 시각/오디오 임팩트
  + length_fit            * 0.05  # 이상 길이(30–75초) 적합도
  - context_penalty               # 맥락 의존도 패널티 (avg > 0.35이면 적용)
  - payoff_weakness_penalty       # 페이오프 약할 때 패널티
)

arc_quality_delta = clamp((arc_quality - 0.3) * 3.0, -1.5, 1.5)
final_score = old_score + arc_quality_delta
```

**winning_signals 목록 예시:**
- `"strong_payoff"` — payoff_strength > 0.6
- `"payoff_exceeds_setup"` — payoff > setup by 0.2
- `"strong_standalone"` — standalone > 0.6
- `"visual_audio_synergy"` — visual_audio > 0.5

---

## 8. 스코어링 공식 전체

**파일:** `backend/app/services/candidate_generation.py` → `score_window()`

### 17개 컴포넌트 스코어 (0–1 정규화, 가중치 합산)

| 컴포넌트 | 가중치 | 공식 |
|----------|--------|------|
| `speech_coverage` | 12% | `merged_speech_duration / window_duration` (≤1.0) |
| `dialogue_density` | 10% | `min(1.0, (cue_count / duration) * 2.8)` |
| `qa_score` | 12% | `0.45 + answer_score*0.55 + payoff*0.25` (question 이벤트 존재 시) |
| `reaction_score` | 12% | `peak_2nd_half_reaction - avg_1st_half_reaction + 0.35` |
| `payoff_score` | 14% | `peak(payoff, emotion, reaction) in last_third + terminal_bonus` |
| `entity_score` | 6% | `intersection(entities) / union(entities)` across events |
| `clarity_score` | 10% | `speech*0.55 + event_bonus*0.25 + terminal_punctuation*0.2` |
| `hook_score` | 10% | `question*0.35 + surprise*0.3 + tension*0.25 + reaction*0.2` (첫 이벤트) |
| `tone_signals` | 6% | `max(comedy, emotion, surprise, tension, reaction)` |
| `cut_density` | 3% | `min(1.0, cuts_inside / max(duration/8, 1))` |
| `visual_audio_bonus` | 5% | `min(vis*0.5 + audio*0.5, clarity*1.2)` |
| `contiguous_bonus` | 가변 | `arc_complete * 0.08` (arc_complete >= 0.25인 경우) |

### 최종 점수 계산

```
raw = speech_cov*0.12 + dialogue_dens*0.10 + qa*0.12 + reaction*0.12
    + payoff*0.14 + entity*0.06 + clarity*0.10 + hook*0.10
    + tone*0.06 + cut_density*0.03 + vis_audio*0.05 + contiguous_bonus

total_score = min(1.0, raw) * 10.0   →  [0.0, 10.0]
```

Arc 재랭크 후 최종:
```
final_score = clamp(total_score + arc_quality_delta, 0.0, 10.0)
```

Vision 재랭크 후 최최종 (VISION_CANDIDATE_RERANK=True):
```
final_score = clamp(final_score + vision_delta, 0.0, 10.0)
```

### 실제 스코어링 예시 (60초 QA 패턴 후보)

```
이벤트 A (0–20s): "왜 그런 거야?" (question_signal=0.7)
이벤트 B (20–50s): "그래서 말이야... 그게 핵심이라고." (payoff=0.8, emotion=0.4)

speech_coverage  = 0.85 * 0.12 = 0.102
dialogue_density = 0.23 * 0.10 = 0.023
qa_score         = 0.825 * 0.12 = 0.099
reaction_score   = 0.75 * 0.12 = 0.090
payoff_score     = 0.50 * 0.14 = 0.070
entity_score     = 0.60 * 0.06 = 0.036
clarity_score    = 0.615 * 0.10 = 0.062
hook_score       = 0.305 * 0.10 = 0.031
tone_signals     = 0.50 * 0.06 = 0.030
cut_density      = 0.40 * 0.03 = 0.012
visual_audio     = 0.50 * 0.05 = 0.025
contiguous_bonus              = 0.040

합계 = 0.620 → total_score = 6.20
arc_quality_delta = (0.44 - 0.3) * 3.0 = +0.42
→ 최종 = 6.62
```

---

## 9. 콘텐츠 생성 서비스

### 9.1 스크립트 생성 (`script_service.py`)

**OpenAI 생성:**

```python
messages = [
  {"role": "system", "content": "JSON 형식으로 쇼츠 스크립트를 생성합니다."},
  {"role": "user", "content": f"""
    후보 정보: {candidate_summary}
    자막 발췌: {transcript_excerpt}
    언어: {language}
    버전 수: {versions}
    반환 형식: {{"drafts": [{{"hook": ..., "body": ..., "cta": ..., "title_options": [...]}}]}}
  """}
]
response = openai.chat.completions.create(
  model=settings.OPENAI_MODEL,
  messages=messages,
  response_format={"type": "json_object"}
)
```

**Mock 폴백 (`ALLOW_MOCK_LLM_FALLBACK=True`):**
```python
hook = f"이 장면이 바로 포인트입니다: {candidate.title_hint}"
body = "겉으로는 차분한데, 사실 이 대화에는..."
cta  = "{channel_style} 톤으로 더 보려면 팔로우!"
title_options = [title_hint, f"{title_hint} ver.{i+1}", "드라마 명장면"]
metadata_json["fallback_reason"] = "missing_openai_api_key" | "rate_limited" | ...
```

**estimated_duration 계산:**
```python
estimated_duration_seconds = max(15.0, len(full_script_text) / 12)
# 12 = 한국어 기준 읽기 속도 (12글자/초)
```

### 9.2 비디오 초안 서비스 (`video_draft_service.py`)

현재 상태: `video_template_renderer.py`는 실제 FFmpeg 기반으로 구현됨. TTS는 OpenAI `gpt-4o-mini-tts` API를 실제 호출하며 API 키 없을 시 FFmpeg silence 폴백.

**내보내기 프리셋:**

| 프리셋 | 해상도 | CRF | 워터마크 |
|--------|--------|-----|---------|
| `shorts_default` | 1080×1920 | 23 | 없음 |
| `review_lowres` | 720×1280 | 30 | "INTERNAL REVIEW" |
| `archive_master` | 원본 유지 | 18 | 없음 |

### 9.3 쇼츠 클립 렌더링 (`short_clip_service.py`)

실제 FFmpeg로 동작하는 유일한 렌더링 서비스.

```python
render_candidate_short_clip(
  candidate_id,
  trim_start, trim_end,          # 시작/종료 시각
  burn_subtitles=True,
  width=1080, height=1920,
  fit_mode="contain",            # "contain" | "cover" | "pad-blur"
  quality_preset="standard",     # "draft" | "standard" | "high"
  subtitle_style={font, colors, alignment},
  subtitle_text_overrides={segment_id: custom_text},
  use_imported_subtitles=False,
  use_edited_ass=False,
  output_kind="final"            # "final" | "preview"
)
```

**처리 흐름:**
1. clip_spans에서 각 구간별 FFmpeg trim 추출
2. 자막 burn-in 적용 (ASS 필터)
3. fit_mode에 따른 스케일/패딩 적용
4. 구간 연결 (concat 필터)
5. H.264 MP4 인코딩

---

## 10. API 엔드포인트 전체

**Base URL:** `http://localhost:8000/api/v1`

### Episodes

| Method | Path | 설명 |
|--------|------|------|
| `POST` | `/episodes` | 에피소드 업로드 (multipart form) |
| `GET` | `/episodes` | 목록 조회 (status?, show_title?, page, page_size) |
| `GET` | `/episodes/{id}` | 상세 조회 |
| `DELETE` | `/episodes/{id}` | 삭제 (파일 + DB) |
| `GET` | `/episodes/{id}/source-video` | 원본 영상 스트리밍 |
| `POST` | `/episodes/{id}/analyze` | 분석 시작 (force_reanalyze?, ignore_cache?) |
| `POST` | `/episodes/{id}/clear-analysis` | 후보·초안·내보내기 전체 삭제 |
| `POST` | `/episodes/{id}/clear-cache` | 프록시·오디오·썸네일·Vision 캐시 삭제 |
| `GET` | `/episodes/{id}/timeline` | shots + transcript segments 반환 |
| `GET` | `/episodes/{id}/jobs` | 에피소드 작업 목록 |
| `GET` | `/episodes/{id}/candidates` | 후보 목록 (status?, min_score?, type?, sort_by?) |

### Candidates & Drafts

| Method | Path | 설명 |
|--------|------|------|
| `GET` | `/candidates/{id}` | 후보 상세 (shots, transcript, scores, metadata) |
| `POST` | `/candidates/{id}/script-drafts` | 스크립트 생성 트리거 |
| `GET` | `/candidates/{id}/script-drafts` | 스크립트 목록 |
| `PATCH` | `/script-drafts/{id}` | 스크립트 수정 |
| `POST` | `/script-drafts/{id}/select` | 스크립트 선택 |
| `POST` | `/candidates/{id}/video-drafts` | 비디오 초안 생성 |
| `GET` | `/candidates/{id}/video-drafts` | 비디오 초안 목록 |
| `GET` | `/video-drafts/{id}` | 비디오 초안 상세 |
| `PATCH` | `/video-drafts/{id}` | 비디오 초안 수정 |
| `POST` | `/video-drafts/{id}/rerender` | 재렌더링 트리거 |
| `POST` | `/video-drafts/{id}/approve` | 승인 |
| `POST` | `/video-drafts/{id}/reject` | 거절 |
| `POST` | `/video-drafts/{id}/exports` | 내보내기 생성 |
| `GET` | `/exports/{id}` | 내보내기 상세 |
| `POST` | `/candidates/{id}/short-clip` | 쇼츠 클립 렌더링 트리거 |
| `GET` | `/candidates/{id}/short-clip/video` | 쇼츠 클립 스트리밍 |

### Jobs

| Method | Path | 설명 |
|--------|------|------|
| `GET` | `/jobs` | 작업 목록 (episode_id?, candidate_id?, type?, status?) |
| `GET` | `/jobs/{id}` | 작업 상세 |

### 보안 주의사항

영상 파일 서빙 엔드포인트(`/source-video`, `/short-clip/video`)는 요청된 경로가 `episode_root()` 내부에 있는지 검증하여 Path Traversal을 방지합니다.

---

## 11. 프론트엔드 구조

**스택:** Next.js 16 App Router + React 19 + TanStack Query v5 + TypeScript 5.9

### 페이지 구조

```
/                          → /episodes 리다이렉트
/episodes                  → 에피소드 목록 (서버 컴포넌트 초기 렌더)
/episodes/new              → 업로드 폼 (클라이언트 컴포넌트)
/episodes/[episodeId]      → 에피소드 상세 + 타임라인 + 작업 진행 상태
/episodes/[episodeId]/candidates → 후보 목록 + 필터
/candidates/[candidateId]  → 후보 상세 (점수, 스팬, 트랜스크립트)
/drafts/[draftId]          → 비디오 초안 편집기
/exports/[exportId]        → 내보내기 다운로드
```

### 핵심 컴포넌트

**`JobsLive`** — React Query로 2초마다 `/jobs?episode_id=...` 폴링, 진행바 표시

**`TimelineViewer`** — shots + transcript segments를 캔버스에 시각화; 후보 스팬 선택 가능

**`CandidateListFilters`** — status, min_score, type, sort_by 필터 UI

**`VideoDraftTemplateEditor`** — TTS voice, aspect ratio, subtitle 스타일 설정

**`CompositeSpanPreview`** — 복합 후보의 다중 스팬 시각화

### 데이터 페칭 패턴

```typescript
// Server Component (초기 로드, SSR)
const episodes = await getEpisodes(searchParams);
return <EpisodeTable episodes={episodes} />;

// Client Component (실시간 폴링)
const { data: jobs } = useQuery({
  queryKey: ["jobs", episodeId],
  queryFn: () => getJobs({ episode_id: episodeId }),
  refetchInterval: 2000,  // 2초마다 폴링
  staleTime: 0,
});
```

### API 클라이언트 (`lib/api.ts`)

모든 요청에 `cache: "no-store"` 적용 (서버 캐시 비활성화로 실시간성 확보).

```typescript
const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    cache: "no-store",
    headers: { "Content-Type": "application/json", ...options?.headers }
  });
  if (!res.ok) throw new ApiHttpError(res.status, await res.text());
  return res.json();
}
```

---

## 12. 스모크 테스트

**파일:** `backend/scripts/smoke_test.py`

외부 의존성 없이 전체 파이프라인을 검증하는 통합 테스트.

### 환경 설정

```python
os.environ["DATABASE_URL"] = "sqlite:///data/smoke/smoke.db"
os.environ["STORAGE_ROOT"] = "storage/smoke"
os.environ["CELERY_TASK_ALWAYS_EAGER"] = "true"  # 동기 실행
os.environ["OPENAI_API_KEY"] = ""                # Mock 강제
```

### 샘플 영상 생성 (FFmpeg)

```bash
ffmpeg -f lavfi -i "color=black:s=1920x1080:r=25" \
       -f lavfi -i "sine=frequency=440:sample_rate=44100" \
       -t 18 \
       -c:v libx264 -crf 23 \
       -c:a aac -b:a 128k \
       sample.mp4
# → 18초, 1920×1080, 440Hz 사인파 오디오
```

### 테스트 시퀀스

**단위 테스트 (Unit Tests):**
1. Tone signals 검증 (영어·한국어 혼합 텍스트)
2. CandidateEvent QA 패턴 스코어링 (question_answer_score > 0.4)
3. 중복 제거 (IOU ≥ 0.52 → 제거)

**통합 테스트 (Integration Tests):**
```
4.  POST /episodes                     → 에피소드 생성 확인
5.  POST /episodes/{id}/analyze        → 분석 트리거 (eager → 즉시 완료)
6.  GET  /jobs/{job_id}               → status="succeeded" 확인
7.  GET  /episodes/{id}/jobs          → 작업 목록 1개 이상
8.  GET  /episodes/{id}/candidates    → 후보 1개 이상
9.  GET  /candidates/{id}             → 상세 구조 확인
10. POST /candidates/{id}/script-drafts → Mock 스크립트 생성
11. GET  /candidates/{id}/script-drafts → 목록 1개 이상
12. PATCH /script-drafts/{id}          → 훅 텍스트 수정
13. POST /script-drafts/{id}/select    → 선택 표시
14. POST /candidates/{id}/video-drafts → 비디오 초안 생성
15. GET  /candidates/{id}/video-drafts → 목록 1개 이상
16. POST /video-drafts/{id}/rerender   → 재렌더링 트리거
17. POST /video-drafts/{id}/approve    → 승인
18. POST /video-drafts/{id}/exports    → 내보내기 생성
19. GET  /exports/{id}                 → 내보내기 상세 확인
```

### 실행

```bash
cd backend
make smoke
# 또는
python scripts/smoke_test.py
```

---

## 13. 스토리지 레이아웃

```
backend/storage/
└── episodes/
    └── {episode_id}/
        ├── source/
        │   ├── source.mp4          (원본 업로드 영상)
        │   └── source.srt          (업로드된 자막, 선택적)
        ├── proxy/
        │   └── analysis_proxy.mp4  (480p, 6fps 분석용 프록시)
        ├── audio/
        │   └── analysis_audio.m4a  (64k 오디오 트랙)
        ├── shots/
        │   ├── 0001.jpg             (샷 썸네일)
        │   ├── 0002.jpg
        │   └── {shot_index:04d}/
        │       ├── frame_001.jpg   (Vision용 keyframe)
        │       └── frame_006.jpg
        ├── candidates/
        │   └── {candidate_id}/
        │       ├── video_drafts/
        │       │   ├── 1/
        │       │   │   └── draft.mp4
        │       │   └── N/...
        │       └── short_clip_1.mp4
        └── cache/
            ├── vision_rerank.json  (Vision 재랭크 캐시)
            └── shots_cache.json    (샷 경계 캐시)

backend/data/
└── smoke/
    └── smoke.db                    (테스트용 SQLite)
```

---

## 14. 메타데이터 JSON 구조

### Episode.metadata_json

```json
{
  "ingest_mode": "ffprobe",
  "media_probe": {
    "status": "ok",
    "duration_seconds": 2580.0,
    "fps": 25.0,
    "width": 1920,
    "height": 1080
  },
  "proxy_transcode": {
    "version": "proxy_v2",
    "status": "completed",
    "mode": "analysis_proxy"
  },
  "shot_detection": {
    "mode": "ffmpeg_scene",
    "status": "completed",
    "shot_count": 87,
    "cache_key": "abc123def456"
  },
  "vision_scan": {
    "status": "completed",
    "frame_count": 522,
    "shots_with_keyframes": 87,
    "version": "vision_scan_v1"
  },
  "transcript_source": "uploaded_subtitle",
  "signals": {
    "algorithm": "signals_v1",
    "transcript_segment_count": 1240,
    "shot_count": 87,
    "estimated_speech_timeline_ratio": 0.68,
    "commentary_friendly": true
  },
  "vision_rerank": {
    "status": "completed",
    "applied_candidates": 8,
    "model": "gpt-4.1"
  }
}
```

### Candidate.metadata_json

```json
{
  "generated_by": "structure_heuristic_v2",
  "arc_form": "contiguous",
  "candidate_track": "dialogue",
  "window_reason": "question_answer",
  "transcript_excerpt": "왜 그런 거야?... 그래서 말이야...",
  "dominant_entities": ["주인공", "상대역", "당신"],
  "clip_spans": [
    {"start_time": 1234.5, "end_time": 1294.5, "order": 0, "role": "main"}
  ],
  "source_events": [
    {
      "start_time": 1234.5,
      "end_time": 1254.5,
      "text": "왜 그런 거야?",
      "event_kind": "question",
      "tone_signals": {
        "question_signal": 0.7,
        "reaction_signal": 0.2,
        "payoff_signal": 0.0,
        "emotion_signal": 0.3,
        "comedy_signal": 0.0,
        "tension_signal": 0.4,
        "surprise_signal": 0.1
      }
    }
  ],
  "speech_coverage": 0.85,
  "question_answer_score": 0.825,
  "reaction_shift_score": 0.75,
  "payoff_end_weight": 0.50,
  "entity_consistency": 0.60,
  "standalone_clarity": 0.615,
  "hookability": 0.305,
  "ranking_focus": "setup_payoff",
  "vision_rerank_applied": true,
  "vision_score_delta": 0.8,
  "rerank_applied": true,
  "rerank_provider": "heuristic_arc_v1",
  "winning_signals": ["strong_payoff", "payoff_exceeds_setup"],
  "arc_continuity": 0.72,
  "length_fit": 0.95
}
```

---

## 15. 한계 및 미구현 사항

### 명시적 미구현 (Stub/Mock)

| 기능 | 현재 상태 | 파일 | 구현 계획 |
|------|-----------|------|-----------|
| TTS 렌더링 | **구현됨** — OpenAI `gpt-4o-mini-tts` 호출, API 키 없으면 silence 폴백 | `tts_service.py` | — |
| 비디오 편집 템플릿 | **구현됨** — FFmpeg ASS 자막 번인·텍스트 슬롯·인트로/아웃트로 TTS 세그먼트 | `video_template_renderer.py` | — |
| 오디오 고급 분석 | FFmpeg astats RMS 기본 구현, spectral·화자분리 미구현 | `candidate_audio_signals.py` | plan.md §8.4-B |
| LLM Arc 판정 | `llm_arc_judge()` noop | `candidate_rerank.py` | plan.md §8.2 |
| ASR (음성→텍스트) | 미구현, 업로드 SRT만 지원 | — | plan.md §8.1 |
| Entity·Coreference | 단순 빈도 기반 | `candidate_events.py` | plan.md §8.5 |
| 후보 품질 평가 체계 | 없음 | — | plan.md §9.4 |
| 성능 계측 | 없음 | — | plan.md §9.5 |

### 설계 제약

| 제약 | 값/조건 |
|------|--------|
| 최대 후보 수 (에피소드당) | 14개 (MAX_CANDIDATES) |
| Vision 적용 최대 후보 수 | 8개 (VISION_MAX_CANDIDATES_PER_EPISODE) |
| 윈도우 길이 범위 | 30–180초 |
| 최대 샷 수 | 100개 (MAX_SHOTS) |
| 후보당 최대 프레임 수 | 6개 (VISION_MAX_FRAMES_PER_CANDIDATE) |
| 복합 후보 최대 세그먼트 | 3개 |
| 복합 후보 최대 합산 길이 | 64초 |
| 세그먼트 간 유효 간격 | 6–420초 |
| micro_event 수 경고 임계값 | > 500개 (beam 탐색 O(n²) 위험) |
| beam_explored_states 경고 | > 50,000 (시간 초과 위험) |

### MVP 외 범위 (의도적 제외)

아래 항목은 현재 시스템 범위 밖이며, 추후 필요성 확인 후 재검토:

- **멀티유저·권한 관리 고도화** — 단일 운영자 시스템으로 충분
- **저작권 감지** — 내부 편집 보조 도구 범위를 벗어남
- **실시간 협업** — 현재 운영 규모에서 불필요
- **완전 무인 자동 배포** — 사람의 검수가 필수
- **YouTube/SNS 자동 업로드** — 타당성 조사 후 결정 (할당량 제한: ~6건/일)

### Canonical Schema (고정 인터페이스)

아래 Enum과 metadata key 목록은 서비스 간 계약으로 관리해야 함. 변경 시 관련 서비스를 일괄 수정.

- **candidate_track:** `dialogue` | `visual` | `audio`
- **arc_form:** `contiguous` | `composite`
- **clip_span role (CORE_ROLES):** `core_setup` | `core_payoff` | `core_escalation` | `core_reaction` | `core_dialogue` | `core_followup` | `main` | `setup` | `payoff` | `reaction` | `followup` | `dialogue`
- **clip_span role (SUPPORT_ROLES):** `support_pre` | `support_post` | `support_bridge`
- **필수 metadata_json 키:** `generated_by`, `arc_form`, `candidate_track`, `clip_spans`, `transcript_excerpt`, `dominant_entities`, `dedupe_tokens`, `window_reason`, `ranking_focus`

상세 정의는 plan.md 부록 C 참조.

### 코드 내 주요 TODO/주석

- `config.py`: `CANDIDATE_RERANK_LLM` 레거시 플래그 — "true여도 새 비전 재랭크를 켭니다"
- `candidate_rerank.py`: `llm_arc_judge()` 함수는 현재 noop; plan.md §8.2에서 구현 계획
- entity 추출: 대명사 필터링 미흡 — "그", "she" 등이 dominant_entities에 포함될 수 있음 (plan.md §8.5)

---

*보고서 작성 기준: 2026-03-30*
*분석 대상 브랜치: main / 본문 기준 커밋 `b1b1926`*
