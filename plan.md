# 쇼츠 후보 자동 생성 파이프라인 상세 계획

> 장편 드라마 에피소드(또는 영화)를 분석해 9:16 세로형 쇼츠 후보 클립을 자동 생성하는 시스템의 전체 설계 및 구현 계획.
> 실제 코드베이스(`backend/app/services/`, `backend/app/tasks/`) 기반으로 작성.

---

> **남은 핵심 과제 (다음 우선순위)**
>
> 1. **단위 테스트 작성** — tone_signals·QA 스코어·Arc 탐색·IOU dedup 4개 케이스 (`§8.2`)
> 2. **통합 테스트 구현** — 실 SRT+영상 파이프라인 E2E 테스트 (`§8.3`)
> 3. **평가셋 기반 스코어링 가중치 튜닝** — 실 드라마 에피소드로 Recall@K 측정 후 ScoringWeights 프로파일 최적화
> 4. **Speaker Diarization 도입 검토** — pyannote.audio 의존성 평가 후 화자 레이블 품질 개선
> 5. **YouTube 자동 업로드** — 채널 할당량 확인 후 구현 (`§8.6` 설계 완료)

---

## 목차

1. [현재 구현 상태 진단](#1-현재-구현-상태-진단)
2. [전체 파이프라인 설계](#2-전체-파이프라인-설계)
3. [Phase 1 — 분석 파이프라인](#3-phase-1--분석-파이프라인)
4. [Phase 2 — 후보 생성 엔진](#4-phase-2--후보-생성-엔진)
5. [Phase 3 — 스코어링 시스템 상세](#5-phase-3--스코어링-시스템-상세)
6. [Phase 4 — Vision·LLM 정제](#6-phase-4--visionllm-정제)
7. [Phase 5 — 렌더링 파이프라인 완성](#7-phase-5--렌더링-파이프라인-완성)
8. [테스트 전략](#8-테스트-전략)
9. [변경 이력 / 최근 구현 요약](#9-변경-이력--최근-구현-요약)
- [부록 A. 핵심 데이터 구조](#부록-a-핵심-데이터-구조)
- [부록 B. 환경 설정 빠른 참조](#부록-b-환경-설정-빠른-참조)
- [부록 C. Canonical Schema & Vocabulary](#부록-c-canonical-schema--vocabulary-고정-인터페이스)
- [부록 D. 기술 분석 상세](#부록-d-기술-분석-상세)

---

## 1. 현재 구현 상태 진단

### 1.1 완성된 구성요소

| 구성요소 | 파일 | 상태 |
|----------|------|------|
| FFmpeg 프록시 트랜스코딩 | `proxy_transcoding.py` | ✅ 완성 |
| Scene 감지 (샷 경계) | `shot_detection.py` | ✅ 완성 |
| Keyframe 추출 | `keyframe_extraction.py` | ✅ 완성 |
| SRT/WebVTT 자막 파싱 | `subtitle_parse.py` | ✅ 완성 |
| Whisper ASR 통합 | `asr_service.py` | ✅ 완성 (faster-whisper/openai-whisper 폴백) |
| 언어 시그널 (키워드 + 임베딩) | `candidate_language_signals.py` | ✅ 완성 (ML 임베딩 `score_window()` live path 연결; `EMBEDDING_SIGNALS_ENABLED=true` + API 키 시 활성, 기본 비활성) |
| Entity 강화 (NER + 화자) | `entity_service.py` | ✅ 완성 |
| Micro-event 생성 | `candidate_events.py` | ✅ 완성 |
| 서사 역할 점수 | `candidate_role_scoring.py` | ✅ 완성 |
| 구조 시그널 (QA/payoff/reaction) | `candidate_structure_signals.py` | ✅ 완성 |
| 시각 시그널 | `candidate_visual_signals.py` | ✅ 완성 |
| 오디오 에너지 프로파일 v2 | `candidate_audio_signals.py` | ✅ 완성 (Track C `generate_audio_seeds_live()` ebur128 기본 경로) |
| 오디오 고급 분석 (librosa) | `audio_analysis_service.py` | ✅ 완성 (Track C optional 보정 연결; `AUDIO_ANALYSIS_BACKEND=librosa/auto` 시 활성, 기본 비활성) |
| 윈도우 스코어링 (3-Track + A/B) | `candidate_generation.py` | ✅ 완성 (ScoringWeights 프로파일) |
| 빔 서치 Arc 탐색 | `candidate_arc_search.py` | ✅ 완성 |
| 복합 후보 생성 (2-span + 3-span) | `composite_candidate_generation.py` | ✅ 완성 |
| Arc 기반 재랭크 + LLM Arc Judge | `candidate_rerank.py` | ✅ 완성 (gpt-4.1-mini, 기본 비활성) |
| Vision 재랭크 v2 (GPT-4.1) | `vision_candidate_refinement.py` | ✅ 완성 (한국어 v2 프롬프트) |
| TTS 렌더링 | `tts_service.py` | ✅ 완성 (OpenAI gpt-4o-mini-tts + silence 폴백) |
| 비디오 템플릿 렌더러 | `video_template_renderer.py` | ✅ 완성 (FFmpeg ASS 자막·텍스트 슬롯·TTS) |
| ASR (Whisper) | `asr_service.py` | ✅ 완성 (기본 비활성, `ASR_ENABLED=True` 필요) |
| 스크립트 생성 (OpenAI) | `script_service.py` | ✅ 완성 (Mock fallback 포함) |
| 쇼츠 클립 FFmpeg 렌더 | `short_clip_service.py` | ✅ 완성 |
| ASS 자막 burn-in | `subtitle_exchange.py` | ✅ 완성 |
| Celery 파이프라인 체인 | `tasks/pipelines.py` | ✅ 완성 |
| 성능 계측 (perf dict) | `analysis_service.py` | ✅ 완성 |
| 오프라인 평가 스크립트 | `scripts/evaluate_candidates.py` | ✅ 완성 |

### 1.2 MVP 외 범위 (선택적 미구현)

| 구성요소 | 파일 | 현재 상태 |
|----------|------|-----------|
| **Speaker Diarization** | 없음 | MVP 외 범위 (pyannote.audio 의존성 큼) |
| **YouTube 자동 업로드** | 없음 | MVP 외 범위 (할당량 제한 ~6개/일) |

### 1.3 MVP 외 범위 (명시적 제외)

| 항목 | 이유 |
|------|------|
| 멀티유저·권한관리 고도화 | 단일 운영자 시스템으로 충분 |
| 저작권 감지 | 내부 편집 보조 도구 범위를 벗어남 |
| 실시간 협업 | 현재 운영 규모에서 불필요 |
| 완전 무인 자동 배포 | 사람의 검수가 필수 |
| YouTube/SNS 자동 업로드 | 타당성 조사 후 결정 (Section 9 참조) |
| Speaker Diarization | pyannote.audio 의존성 크므로 필요성 검증 후 |

### 1.4 핵심 제약값

```python
# candidate_generation.py
MIN_WINDOW_SEC = 30.0    # 윈도우 최소 30초
MAX_WINDOW_SEC = 180.0   # 윈도우 최대 180초
MAX_CANDIDATES = 14      # 에피소드당 최대 후보 수
NMS_IOU_THRESHOLD = 0.52
TEXT_DEDUPE_JACCARD_THRESHOLD = 0.82

# composite_candidate_generation.py
MAX_COMPOSITE_CANDIDATES = 10
MAX_TOTAL_DURATION_SEC = 64.0     # 2-span 복합 최대 합산
MAX_TRIPLE_DURATION_SEC = 90.0    # 3-span 복합 최대 합산 (신규)
MIN_GAP_SEC = 6.0
MAX_GAP_SEC = 420.0

# vision_candidate_refinement.py
VISION_MAX_CANDIDATES = 8   # Vision 적용 최대 후보 수 (settings)
VISION_MAX_FRAMES = 6       # 후보당 최대 프레임 수 (settings)

# candidate_arc_search.py
BEAM_WIDTH = 16
MAX_ARC_DEPTH = 4
MAX_GAP_SEC = 300.0
CONTIGUOUS_GAP_SEC = 12.0
```

---

## 2. 전체 파이프라인 설계

### 2.1 데이터 흐름도

```
[원본 MP4 + 선택적 SRT]
          │
          ▼
┌─────────────────────────────────────┐
│  Phase 1: 분석 파이프라인           │
│                                     │
│  ingest_episode                     │
│    → ffprobe 메타데이터             │
│  transcode_proxy                    │
│    → 480p/6fps 프록시 생성          │
│  detect_shots                       │
│    → FFmpeg scene 감지 (임계값 0.32)│
│  extract_keyframes                  │
│    → 샷당 6프레임 추출              │
│  extract_transcript                 │
│    → SRT 파싱 / Whisper ASR (선택) │
│  compute_signals                    │
│    → speech ratio, cut density 등   │
└─────────────────────────────────────┘
          │
          ▼ (Shot[], TranscriptSegment[])
┌─────────────────────────────────────┐
│  Phase 2: 후보 생성 엔진            │
│                                     │
│  build_micro_events()               │
│    → 자막 큐 → CandidateEvent[]     │
│                                     │
│  3-Track Seed 생성:                 │
│  ├─ Track A: _enumerate_windows()   │
│  │    → 대화 구조 윈도우 시드       │
│  ├─ Track B: generate_visual_seeds()│
│  │    → 컷 밀도·반응샷 시드         │
│  └─ Track C: generate_audio_seeds() │
│       → RMS 에너지 스파이크 시드     │
│                                     │
│  score_window() × N seeds           │
│    → ScoredWindow[] (raw scores)    │
│                                     │
│  build_composite_candidates()       │
│    → beam_search_arcs() [Phase 1]  │
│    → pair heuristic [Phase 2]      │
│    → 3-span triple [Phase 3]       │
│    → composite ScoredWindow[]       │
│                                     │
│  rerank_scored_windows()            │
│    → arc_quality_delta 적용         │
│                                     │
│  dedupe_scored_windows()            │
│    → IOU NMS + Jaccard dedupe       │
│    → 최대 14개 Candidate           │
└─────────────────────────────────────┘
          │
          ▼ (ScoredWindow[14])
┌─────────────────────────────────────┐
│  Phase 4: Vision·LLM 정제           │
│                                     │
│  refine_candidates_with_vision()    │
│    → 상위 8개 × GPT-4V 재랭크       │
│    → score_delta [-1.5, +1.5]       │
│                                     │
│  llm_arc_judge() [기본 비활성]      │
│    → gpt-4.1-mini 서사 판정        │
│    → LLM_ARC_JUDGE_ENABLED=True 시│
└─────────────────────────────────────┘
          │
          ▼ (Candidate DB 저장)
┌─────────────────────────────────────┐
│  Phase 5: 사용자 워크플로우         │
│                                     │
│  ScriptDraft 생성 (OpenAI/Mock)     │
│  VideoDraft 렌더링 (FFmpeg 실제 동작)│
│  ShortClip 렌더링 (FFmpeg 실제 동작)│
│  Export 패키징                      │
└─────────────────────────────────────┘
```

### 2.2 Celery 태스크 체인 구조

```python
# tasks/pipelines.py - launch_analysis_pipeline()
chain(
    ingest_episode.s(episode_id, job_id, ignore_cache),   # 10% 진행
    transcode_proxy.s(job_id),                            # 30%
    detect_shots.s(job_id),                               # 45%
    extract_keyframes.s(job_id),                          # 52%
    extract_or_generate_transcript.s(job_id),             # 60%
    compute_signals.s(job_id),                            # 75%
    generate_candidates.s(job_id),                        # 90% → 100%
).apply_async()
```

각 태스크는 이전 태스크의 `payload: dict`를 입력으로 받아 `{**payload, "새_키": 결과}` 형식으로 전달.
실패 시 `_handle_step_failure()`가 Job 상태를 FAILED로 전환하고 Episode 상태를 FAILED로 마킹.

---

## 3. Phase 1 — 분석 파이프라인

### 3.1 FFmpeg 프록시 트랜스코딩 (`proxy_transcoding.py`)

**목적:** 원본 고화질 영상(수 GB) 대신 분석용 소형 프록시로 처리 속도 극대화.

```python
# 프록시 영상 생성
ffmpeg_cmd = [
    "ffmpeg", "-i", str(src_path),
    "-vf", f"scale='min(iw,{settings.proxy_max_width})':-2",  # 480p 축소
    "-r", str(settings.proxy_video_fps),    # 6 FPS
    "-crf", str(settings.proxy_video_crf),  # CRF 31 (저화질 고속)
    "-preset", "veryfast",
    "-an",  # 오디오 제거 (별도 추출)
    str(proxy_path),
]

# 오디오 별도 추출 (64k AAC)
ffmpeg_audio_cmd = [
    "ffmpeg", "-i", str(src_path),
    "-vn", "-acodec", "aac", "-ab", "64k",
    str(audio_path),
]
```

**캐싱 전략:** `cache_utils.file_signature(path)`(크기 + mtime 해시)를 기반으로 동일 파일 재처리 방지.
`metadata_json["proxy_transcode"]["status"]` = `"completed"` | `"cached"` | `"fallback"`

---

### 3.2 샷 감지 알고리즘 (`shot_detection.py`)

```python
# FFmpeg scene filter 활용
ffmpeg_cmd = [
    "ffmpeg", "-i", str(proxy_path),
    "-vf", f"select='gt(scene\\,{settings.ffmpeg_scene_threshold})',showinfo",
    "-f", "null", "-",
]
# 기본 임계값: 0.32
```

**샷 후처리 규칙:**
1. 0.28초 미만 간격의 연속 샷 → 병합
2. 최대 100개 상한 (`MAX_SHOTS`)
3. 감지 실패 시 에피소드를 균등 분할로 폴백

**임계값 선택 가이드:**
- `0.2` → 과도하게 많은 샷 (편집 잡음)
- `0.32` → 실용적 균형점 (약 80–120샷 / 45분 에피소드)
- `0.5` → 너무 적은 샷 (장면 전환 누락)

---

### 3.3 Keyframe 추출 (`keyframe_extraction.py`)

샷당 6프레임을 균등 간격으로 추출. Vision 재랭크(`vision_candidate_refinement.py`)의 `_candidate_frame_paths()`가 후보 윈도우 내 모든 프레임에서 균등 6개를 선택.

저장 경로: `storage/episodes/{id}/shots/{shot_index:04d}/frame_{n:03d}.jpg`

---

### 3.4 자막 파싱 (`subtitle_parse.py`)

```python
SRT_CUE_RE = re.compile(
    r"(\d+)\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n([\s\S]*?)(?=\n\n|\Z)",
    re.MULTILINE,
)

def parse_srt(text: str) -> list[SubtitleCue]:
    cues = []
    for match in SRT_CUE_RE.finditer(text):
        start = _ts_to_seconds(match.group(2))
        end   = _ts_to_seconds(match.group(3))
        text  = match.group(4).strip()
        cues.append(SubtitleCue(start=start, end=end, text=text))
    return cues
```

SRT/WebVTT 업로드 파일 지원. ASR 미설정 시 자막 없이도 파이프라인 실행 가능 (빈 segment 목록).

---

### 3.5 오디오 에너지 프로파일 (`candidate_audio_signals.py`, `audio_analysis_service.py`)

Track C 씨앗 생성의 기반. **v2: FFmpeg `ebur128` 단일 패스** (구 astats N×호출 대비 처리 시간 1/100 이하).

```python
def extract_audio_energy_profile_v2(audio_path, duration_seconds, segment_length=5.0):
    """단일 FFmpeg 호출로 전체 에피소드 라우드니스 프로파일 추출."""
    proc = subprocess.run([
        "ffmpeg", "-i", str(audio_path),
        "-af", "ebur128=framelog=verbose",
        "-f", "null", "-",
    ], capture_output=True, text=True, timeout=300)
    return _parse_ebur128_output(proc.stderr, segment_length)
    # 폴백: ebur128 결과 없으면 astats 방식으로 전환

def compute_audio_impact_scores(energy_profile):
    # silence_to_spike * 0.4 + energy_burst * 0.35 + volume_jump * 0.25
    ...
```

오디오 임팩트 ≥ 0.2인 구간을 앵커로, pre_pad(3/6/10초) + post_pad(5/10/20초) 조합으로 WindowSeed 생성. 최대 10개 시드 (`generate_audio_seeds_v2()`).

**고급 오디오 분석 (`audio_analysis_service.py`):** `AUDIO_ANALYSIS_BACKEND` 설정으로 선택.
```python
def extract_audio_features(audio_path, *, backend="auto") -> list[dict]:
    # backend="librosa": RMS, spectral_centroid, ZCR, MFCC(13차원)
    # backend="ffmpeg":  rms_db만 (ebur128 기반)
    # backend="auto":    librosa 시도 → ImportError면 ffmpeg 폴백

def compute_audio_emotion_scores(segments) -> list[dict]:
    # tension_hint = centroid / max_centroid  (긴장도 지표)
    # speech_likelihood = (zcr - 0.05) / 0.15  (음성 확률)
```

---

## 4. Phase 2 — 후보 생성 엔진

### 4.1 Micro-Event 생성 (`candidate_events.py`)

자막 큐(`TranscriptSegment[]`)를 의미 단위인 `CandidateEvent`로 병합.

**경계 조건 (`_is_boundary`):**
```python
def _is_boundary(current_text, next_text, *, current_duration, gap_to_next) -> bool:
    if current_duration >= 18.0:                                    return True
    if gap_to_next >= 1.8 and current_duration >= 4.0:             return True
    if current_text.strip().endswith(("?","!",".","?!","!?"))
       and current_duration >= 4.0:                                return True
    if tone_signals(current_text)["reaction_signal"] >= 0.45
       and current_duration >= 4.0:                                return True
    if tone_signals(current_text)["payoff_signal"] >= 0.45
       and current_duration >= 4.0:                                return True
    if question_signal >= 0.45 and answer_marker_score(next_text) >= 0.5:
                                                                   return True
    return False
```

**이벤트 역할 점수 (`candidate_role_scoring.py`):**

```python
# setup_score: 질문·긴장 존재 여부
setup = (
    signals["question_signal"] * 0.35
    + signals["tension_signal"] * 0.25
    + _marker_hit(text, SETUP_MARKERS) * 0.2
    + (0.15 if text.strip().endswith("?") else 0.0)
    + (0.05 if is_first else 0.0)
)

# payoff_score: 결론·감정·반응 존재 여부
payoff = (
    signals["payoff_signal"] * 0.35
    + signals["emotion_signal"] * 0.15
    + signals["reaction_signal"] * 0.15
    + _marker_hit(text, PAYOFF_MARKERS) * 0.2
    + (0.1 if is_last else 0.0)
    + (0.05 if event_kind in {"payoff","reaction","emotion"} else 0.0)
)

# context_dependency_score: 앞 맥락 없이는 이해 불가 정도
ctx_dep = (
    pronoun_ratio * 0.4              # "그", "she", "they" 등 지시어 비율
    + _marker_hit(text, CONTEXT_DEP_MARKERS) * 0.3  # "아까", "before" 등
    + (0.15 if not dominant_entities else 0.0)
    + (0.15 if cue_count <= 1 and len(text) < 30 else 0.0)
)
```

---

### 4.2 3-Track 윈도우 생성 (`candidate_generation.py`)

#### Track A: 대화 구조 기반 (`_enumerate_windows`)

```python
def _enumerate_windows(timeline_end, segments, shots) -> list[WindowSeed]:
    events = build_micro_events(segments, shots)

    for start_idx in range(len(events)):
        for end_idx in range(start_idx, min(len(events), start_idx + 10)):
            event_slice = events[start_idx : end_idx + 1]
            duration = event_slice[-1].end_time - event_slice[0].start_time
            if duration < 30.0: continue
            if duration > 180.0: break

            reason = _event_window_reason(event_slice)
            if reason:
                seeds.append(WindowSeed(..., window_reason=reason))

    # 이벤트 없으면 샷 경계 폴백
    if not seeds:
        return _shot_window_fallback(shots, timeline_end)
```

**`_event_window_reason` 우선순위:**
```
qa_score >= 0.45    → "question_answer"
reaction >= 0.42    → "reaction_shift"
payoff >= 0.45      → "payoff_end"
hook >= 0.45 (이벤트 ≤ 4개) → "hook_open"
마지막 이벤트 종류  → "tail_{reaction|payoff|emotion|tension}"
이벤트 ≤ 3개        → "compact_dialogue_turn"
그 외               → None (폐기)
```

#### Track B: 시각 임팩트 (`candidate_visual_signals.py`)

- **컷 밀도 스파이크:** 로컬 컷 빈도 > 에피소드 평균 × 1.5인 구간
- **반응샷 패턴:** 3개 이상 연속 2초 미만 샷 (CUT-CUT-CUT)
- **저대사 고시각:** speech_coverage < 0.3 AND cut_density > 평균

#### Track C: 오디오 반응 (`candidate_audio_signals.py`)

오디오 임팩트 ≥ 0.2인 세그먼트를 앵커로 패딩 적용해 시드 생성. 최대 10개.

---

### 4.3 윈도우 스코어링 (`score_window`, `candidate_generation.py`)

```python
def score_window(seed, segments, shots, *, episode_avg_cut_rate, timeline_end):
    # 기본 측정값
    speech_coverage = _merged_speech_coverage(segments, seed.start_time, seed.end_time)
    cuts_inside     = _cuts_inside(shots, seed.start_time, seed.end_time)
    events          = seed.events

    # 구조 시그널 (candidate_structure_signals.py)
    qa_score        = question_answer_score(events)
    reaction_score  = reaction_shift_score(events)
    payoff_score    = payoff_end_weight(events)
    entity_score    = entity_consistency(events)
    clarity_score   = standalone_clarity(events, speech_coverage)
    hook_score      = hookability(events)

    # 시각/오디오 보너스 (clarity에 의해 상한 제한)
    visual_audio_bonus = min(
        visual_impact * 0.5 + audio_impact * 0.5,
        max(clarity_score, 0.3) * 1.2,
    )

    # contiguous arc 완성도 보너스
    single_arc_complete = min(1.0,
        first_event.setup_score * 0.3
        + last_event.payoff_score * 0.4
        + entity_score * 0.3
    ) if len(events) >= 2 else 0.0
    contiguous_bonus = single_arc_complete * 0.08 if single_arc_complete >= 0.25 else 0.0

    # 가중치 합산 → [1.0, 10.0]
    normalized = min(1.0,
        speech_coverage * 0.12
        + dialogue_density * 0.10
        + qa_score * 0.12
        + reaction_score * 0.12
        + payoff_score * 0.14
        + entity_score * 0.06
        + clarity_score * 0.10
        + hook_score * 0.10
        + max(comedy, emotion, surprise, tension, reaction) * 0.06
        + cut_density_score * 0.03
        + visual_audio_bonus * 0.05
        + contiguous_bonus,
    )
    total_score = round(max(1.0, normalized * 10.0), 2)

    # clip_spans: pad_spans_to_minimum()으로 최소 30초 보장
    from candidate_spans import pad_spans_to_minimum
    padded_spans, support_added = pad_spans_to_minimum(core_spans, ...)
```

---

### 4.4 빔 서치 Arc 탐색 (`candidate_arc_search.py`)

setup_score가 높은 이벤트(상위 20개)를 씨앗으로, 2–4개 이벤트 체인을 탐색.

```python
# beam_search_arcs() 핵심 구조
BEAM_WIDTH = 16
MAX_ARC_DEPTH = 4
MAX_GAP_SEC = 300.0
CONTIGUOUS_GAP_SEC = 12.0

seed_events = sorted(events, key=lambda e: e.setup_score, reverse=True)[:20]
beams = [[e] for e in seed_events]

for depth in range(MAX_ARC_DEPTH - 1):
    next_beams = []
    for beam in beams:
        tail = beam[-1]
        for candidate_event in events:
            gap = candidate_event.start_time - tail.end_time
            if gap <= 0 or gap > MAX_GAP_SEC: continue
            # 간격 클 때 entity 겹침 필요
            if gap > CONTIGUOUS_GAP_SEC and entity_overlap(tail, candidate_event) < 0.05: continue

            new_beam = beam + [candidate_event]
            scores = _score_arc(new_beam)

            # 종료: payoff/reaction 충분하거나 최대 깊이
            if candidate_event.payoff_score >= 0.15 or candidate_event.reaction_score >= 0.3:
                completed_arcs.append(ArcCandidate(new_beam, scores, arc_form, ...))

            next_beams.append((scores["total_arc_score"], new_beam))

    beams = top_k_beams(next_beams, k=BEAM_WIDTH)
```

**Arc 스코어 공식 (`_score_arc`):**
```python
total = (
    first_event.setup_score       * 0.20
    + avg_escalation_score        * 0.10
    + last_event.payoff_score     * 0.25
    + setup_to_payoff_delta       * 0.10   # max(0, payoff - setup*0.3)
    + arc_continuity_score        * 0.10~0.15  # entity 겹침 연속성
    + avg_standalone_score        * 0.10
    + visual_audio_bonus          * 0.10
    - context_penalty                      # avg_ctx_dep > 0.3 패널티
)
arc_form = "contiguous" if all(gap(i,i+1) <= 12s) else "composite"
```

---

### 4.5 복합 후보 생성 (`composite_candidate_generation.py`)

비연속 세그먼트를 묶는 복합 후보. 3단계 생성.
- **Phase 1:** `beam_search_arcs()` 결과 → `ArcCandidate` → `ScoredWindow`
- **Phase 2:** 최고 40개 윈도우의 쌍(pair) 휴리스틱 폴백
- **Phase 3:** 상위 20개 윈도우의 3-스팬 트리플 (setup-escalation-payoff, MAX_TRIPLE_DURATION_SEC=90.0)

**Phase 3 — 3-스팬 트리플 조건:**
```python
# _build_triple_composite(left, mid, right, *, timeline_end)
# - gap1 = mid.start - left.end: 6s ≤ gap ≤ 420s
# - gap2 = right.start - mid.end: 6s ≤ gap ≤ 420s
# - total_duration ≤ 90.0s AND ≥ 30.0s
# - coherence(entity Jaccard) ≥ 0.10
# - 역할: left→core_setup, mid→core_escalation, right→core_payoff
```

**Phase 2 — 쌍 스코어 공식:**
```python
total_score = (
    (left.total_score + right.total_score) / 2.0
    + overlap_score * 0.9           # 텍스트 토큰 Jaccard
    + entity_overlap * 0.65
    + question_answer_match * 0.8
    + reaction_shift * 0.55
    + (0.35 if same_focus else 0.0)
    + gap_bonus                     # 0.35 (≤45s), 0.18 (≤120s), 0.0 (>120s)
    - duration_penalty              # >50s일 때 패널티
    - min(0.45, gap / 360.0)        # 간격 패널티
)
# 조건: gap 6–420s, total_duration ≤ 64s
```

---

### 4.6 중복 제거 NMS (`dedupe_scored_windows`)

```python
def _is_duplicate_candidate(candidate, kept) -> bool:
    # 방법 1: 시간 IOU >= 0.52
    iou = overlap / union  # 시간 겹침
    if iou >= 0.52: return True

    # 방법 2: 텍스트 Jaccard >= 0.82 AND 시간 근접
    jaccard = |A ∩ B| / |A ∪ B|  # dedupe_tokens 기반
    if jaccard >= 0.82:
        if temporal_overlap >= 8.0 or start_gap <= 20.0: return True

    return False

# 점수 내림차순 정렬 후 greedy 선택 → 최대 14개
```

---

## 5. Phase 3 — 스코어링 시스템 상세

### 5.1 17개 컴포넌트 점수 전체 공식

| 컴포넌트 | 가중치 | 공식 | 구현 파일 |
|----------|--------|------|-----------|
| `speech_coverage` | 12% | `merged_speech_sec / window_sec` (≤1) | `candidate_generation.py` |
| `dialogue_density` | 10% | `min(1, (cue_count/sec) * 2.8)` | `candidate_structure_signals.py` |
| `qa_score` | 12% | `0.45 + answer_score*0.55 + payoff*0.25` | `candidate_structure_signals.py` |
| `reaction_score` | 12% | `late_reaction - early_reaction + 0.35` | `candidate_structure_signals.py` |
| `payoff_score` | 14% | `peak(payoff+emotion+reaction)/3 in last_third + terminal_bonus` | `candidate_structure_signals.py` |
| `entity_score` | 6% | `intersection(entities) / union(entities)` | `candidate_structure_signals.py` |
| `clarity_score` | 10% | `speech*0.55 + event_bonus*0.25 + terminal_punct*0.2` | `candidate_structure_signals.py` |
| `hook_score` | 10% | `question*0.35 + surprise*0.3 + tension*0.25 + reaction*0.2` | `candidate_structure_signals.py` |
| `tone_signals` | 6% | `max(comedy, emotion, surprise, tension, reaction)` | `candidate_language_signals.py` |
| `cut_density` | 3% | `min(1, cuts_inside / max(duration/8, 1))` | `candidate_generation.py` |
| `visual_audio_bonus` | 5% | `min(vis*0.5+audio*0.5, clarity*1.2)` | `candidate_generation.py` |
| `contiguous_bonus` | 가변 | `arc_complete * 0.08` (arc ≥ 0.25만) | `candidate_generation.py` |

### 5.2 구조 시그널 함수 전체 (`candidate_structure_signals.py`)

```python
def question_answer_score(events) -> float:
    """인접 이벤트의 Q→A 패턴 강도."""
    score = 0.0
    for left, right in zip(events, events[1:]):
        if left.tone_signals["question_signal"] >= 0.45:
            score = max(score, min(1.0,
                0.45
                + answer_marker_score(right.text) * 0.55
                + right.tone_signals["payoff_signal"] * 0.25
            ))
    return min(1.0, score)

def reaction_shift_score(events) -> float:
    """후반부 reaction이 전반부보다 얼마나 강한가."""
    split = max(1, len(events) // 2)
    early_level = max((e.tone_signals["reaction_signal"] + e.tone_signals["surprise_signal"]) / 2 for e in events[:split])
    late_level  = max((e.tone_signals["reaction_signal"] + e.tone_signals["surprise_signal"]) / 2 for e in events[split:])
    return max(0.0, min(1.0, late_level - early_level + 0.35))

def payoff_end_weight(events) -> float:
    """마지막 1/3 구간의 payoff 집중도."""
    tail = events[max(0, len(events) - max(1, len(events)//3)):]
    peak = max(
        (e.tone_signals["payoff_signal"] + e.tone_signals["emotion_signal"] + e.tone_signals["reaction_signal"]) / 3
        for e in tail
    )
    terminal_bonus = 0.15 if tail[-1].event_kind in {"reaction","payoff","emotion"} else 0.0
    return min(1.0, peak + terminal_bonus)

def entity_consistency(events) -> float:
    """이벤트 간 공통 엔티티 비율."""
    entity_sets = [set(e.dominant_entities) for e in events if e.dominant_entities]
    if len(entity_sets) < 2: return 0.35 if entity_sets else 0.0
    return len(set.intersection(*entity_sets)) / len(set.union(*entity_sets))

def standalone_clarity(events, speech_coverage) -> float:
    """앞뒤 맥락 없이 독립 이해 가능 정도."""
    event_bonus = min(1.0, len(events) / 4.0)
    terminal_bonus = 0.2 if events[-1].text.strip().endswith(("?","!",".")) else 0.0
    return min(1.0, speech_coverage * 0.55 + event_bonus * 0.25 + terminal_bonus)

def hookability(events) -> float:
    """첫 이벤트의 시청자 호기심 유발 강도."""
    head = events[0]
    return min(1.0,
        head.tone_signals["question_signal"] * 0.35
        + head.tone_signals["surprise_signal"] * 0.3
        + head.tone_signals["tension_signal"] * 0.25
        + head.tone_signals["reaction_signal"] * 0.2
    )
```

### 5.3 Arc 재랭크 델타 (`candidate_rerank.py`)

```python
def _evaluate_arc_quality(window) -> dict:
    setup_strength  = source_events[0]["setup_score"]   # 첫 이벤트
    payoff_strength = source_events[-1]["payoff_score"] # 마지막 이벤트
    setup_to_payoff_delta = max(0, payoff_strength - setup_strength * 0.5)

    # 이상적 길이: 30~75초
    if 30 <= duration <= 75:        length_fit = 1.0
    elif duration < 30:             length_fit = max(0.3, duration / 30)
    else:                           length_fit = max(0.3, 1.0 - (duration - 75) / 120)

    arc_quality = (
        setup_strength          * 0.15
        + payoff_strength       * 0.25
        + setup_to_payoff_delta * 0.15
        + arc_continuity        * 0.10
        + standalone            * 0.15
        + visual_audio_impact   * 0.05
        + length_fit            * 0.05
        - context_penalty               # max(0, avg_ctx_dep - 0.35) * 0.6
        - payoff_weakness_penalty       # 0.15 if payoff < 0.15 and setup >= 0.2
    )

    arc_quality_delta = clamp((arc_quality - 0.3) * 3.0, -1.5, 1.5)
    # final_score = clamp(old_score + delta, 1.0, 10.0)
```

### 5.4 언어 시그널 (`candidate_language_signals.py`)

#### 키워드 기반 ToneSignals (7개)

```python
def _keyword_signal_score(text, keywords) -> float:
    hits = sum(1 for kw in keywords if kw in normalize_text(text))
    punct_bonus = (
        (0.15 if "!" in text else 0.0)
        + (0.12 if "?" in text else 0.0)
        + (0.12 if re.search(r"[!?]{2,}", text) else 0.0)
        + (0.08 if re.search(r"\b[A-Z]{2,}\b", text) else 0.0)
    )
    return min(1.0, hits * 0.2 + punct_bonus)

def tone_signals(text) -> ToneSignals:
    # question_signal: "?" 존재(+0.4) + QUESTION_MARKERS 포함(+0.35)
    # comedy/emotion: max(한국어, 영어) 점수
    return ToneSignals(question_signal=..., comedy_signal=..., ...)
```

#### Entity 추출 강화

```python
_PRONOUN_STOP: frozenset[str]  # 한국어/영어 대명사 + 동사 파편 (약 30개)

def dominant_entities(tokens: list[str], *, limit: int = 5) -> list[str]:
    """_PRONOUN_STOP 필터 + len >= 2 조건. raw token stream 입력 필요."""
```

#### ML 기반 임베딩 시그널

```python
class EmbeddingSignals(TypedDict):
    comedy_emb, emotion_emb, tension_emb, reaction_emb, payoff_emb: float
    embedding_used: bool

_EMBEDDING_ANCHORS: dict[str, list[str]]  # 카테고리별 한국어 앵커 문장 3개

def compute_embedding_signals(text, *, api_key=None, model="text-embedding-3-small") -> EmbeddingSignals:
    """
    - API 키 있으면: 앵커 + 쿼리를 배치 요청 → 코사인 유사도 계산 → [0,1] 정규화
    - API 키 없거나 오류: tone_signals() 결과로 폴백 (embedding_used=False)
    """
```

---

## 6. Phase 4 — Vision·LLM 정제

### 6.1 Vision 재랭크 상세 (`vision_candidate_refinement.py`)

**호출 조건:** `VISION_CANDIDATE_RERANK=True` + `OPENAI_API_KEY` 존재

```python
# 캐시 키 (파일 서명 기반, 프레임 변경 시 자동 무효화)
cache_key = stable_hash({
    "episode_id": episode.id,
    "model": settings.vision_model,
    "prompt_version": settings.vision_prompt_version,
    "window": {"start_time": ..., "end_time": ..., "heuristic_total_score": ...},
    "transcript_excerpt": transcript_excerpt,
    "frames": [file_signature(p) for p in frame_paths],
})

# Vision API 호출 (vision_candidate_rerank_v2 — 한국어 시스템 프롬프트)
response = client.chat.completions.create(
    model="gpt-4.1",
    response_format={"type": "json_object"},
    messages=[
        {"role": "system", "content": """
            당신은 한국 드라마 쇼츠 채널의 편집 전문가입니다.
            반환 JSON 필드:
            score_delta (-1.5..1.5), visual_hook_score (0..10),
            self_contained_score (0..10), emotion_shift_score (0..10),
            thumbnail_strength_score (0..10), vision_reason (한국어 max 140자),
            title_hint (max 90자 or null), note (max 220자 or null)

            ## 강하게 보상 (+score_delta)
            - 웃긴/역설/황당한 상황 (코미디·반전)
            - 감동적·공감 장면 (울컥, 화해, 고백)
            - 강한 감정 폭발, 30~75초 기승전결 완결

            ## 패널티 (-score_delta)
            - 앞 장면 없이 이해 불가, 감정 결말 없이 끊김
            - 어두운 화면, 빈 자막
        """},
        {"role": "user", "content": [
            {"type": "text", "text": json.dumps(candidate_context)},
            *[{"type": "image_url", ...} for frame in frame_paths[:6]],
        ]},
    ],
    temperature=0.25, max_tokens=500,
)

# 점수 적용
delta = clamp(payload["score_delta"], -1.5, 1.5)
new_score = clamp(old_score + delta, 1.0, 10.0)
```

### 6.2 LLM Arc Judge (`candidate_rerank.py`) — ✅ 구현 완료

`LLM_ARC_JUDGE_ENABLED=True`일 때 상위 `LLM_ARC_JUDGE_TOP_K`개(기본 5) 후보에 적용.

```python
def llm_arc_judge(windows, *, top_k=5, provider="openai") -> list[ScoredWindow]:
    """gpt-4.1-mini 기반 서사 품질 판정.
    API 키 없거나 provider="noop"이면 조용히 스킵 (기존 점수 유지).
    """
    for i, window in enumerate(windows[:top_k]):
        context = {
            "title_hint": window.title_hint,
            "duration_sec": window.end_time - window.start_time,
            "transcript_excerpt": ...,
        }
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            response_format={"type": "json_object"},
            messages=[system: _ARC_JUDGE_SYSTEM_PROMPT, user: json.dumps(context)],
            temperature=0.1, max_tokens=300,
        )
        # 응답: arc_closed(bool), standalone(0-10), shorts_fit(0-10),
        #       adjustment([-1.0, 1.0]), reason(str)
        delta = clamp(payload["adjustment"], -1.0, 1.0)
        windows[i] = _apply_llm_adjustment(windows[i], delta, payload)
```

metadata에 `llm_arc_judge_applied`, `llm_arc_judge_model`, `llm_arc_judge_reason` 기록.

---

## 7. Phase 5 — 렌더링 파이프라인 완성

### 7.1 쇼츠 클립 렌더링 (`short_clip_service.py`) — 실제 동작

```python
# _build_video_filter() - 3가지 fit_mode
if fit_mode == "cover":
    base = f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}[composed]"
elif fit_mode == "pad-blur":
    base = (
        "[0:v]split=2[bgsrc][fgsrc];"
        f"[bgsrc]scale={W}:{H}:force_original_aspect_ratio=increase,"
        f"crop={W}:{H},boxblur=20:10[bg];"
        f"[fgsrc]scale={W}:{H}:force_original_aspect_ratio=decrease[fg];"
        "[bg][fg]overlay=(W-w)/2:(H-h)/2[composed]"
    )
else:  # contain (기본)
    base = (
        f"[0:v]scale={W}:{H}:force_original_aspect_ratio=decrease,"
        f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2[composed]"
    )

# ASS 자막 burn-in 추가
if burn_subtitles and has_subs:
    vf += f";[composed]subtitles={ass_file},format=yuv420p[outv]"

# FFmpeg 실행
cmd = [
    "ffmpeg", "-ss", str(trim_start), "-i", str(src),
    "-t", str(duration),
    "-filter_complex", video_filter,
    "-map", "[outv]", "-map", "0:a?",
    "-c:v", "libx264",
    "-preset", quality["preset"],   # veryfast/fast/medium
    "-crf", quality["crf"],         # 30/23/20
    "-c:a", "aac", "-b:a", quality["audio_bitrate"],  # 96k/128k/160k
    "-movflags", "+faststart",
    out_mp4.name,
]
```

**출력 경로:** `storage/episodes/{id}/candidates/{candidate_id}/short_clip_v{version}.mp4`

### 7.2 ASS 자막 생성 (`subtitle_exchange.py`)

```python
# build_ass_for_clip() - TranscriptSegment → ASS
ASS_HEADER = """
[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Style: Default,NanumGothic,72,&H00FFFFFF,&H000000FF,...

[Events]
Format: Layer, Start, End, Style, Text
"""

for seg in segments_in_range:
    start_rel = max(0.0, seg.start_time - trim_start)
    end_rel   = min(duration, seg.end_time - trim_start)
    text = text_overrides.get(seg.id, seg.text)  # 개별 수정 지원
    lines.append(f"Dialogue: 0,{_ass_ts(start_rel)},{_ass_ts(end_rel)},Default,,{text}")
```

### 7.3 내보내기 프리셋 (`video_draft_service.py`)

```python
EXPORT_PRESETS = {
    "shorts_default": {"width": 1080, "height": 1920, "crf": "23", "watermark": None},
    "review_lowres":  {"width": 720,  "height": 1280, "crf": "30", "watermark": "INTERNAL REVIEW"},
    "archive_master": {"width": None, "height": None, "crf": "18", "watermark": None},
}
```

---

## 8. 테스트 전략

### 8.1 기존 스모크 테스트 (`backend/scripts/smoke_test.py`)

```bash
cd backend && make smoke
# 또는: python scripts/smoke_test.py
```

**환경:**
```python
os.environ["DATABASE_URL"]           = "sqlite:///data/smoke/smoke.db"
os.environ["CELERY_TASK_ALWAYS_EAGER"] = "true"
os.environ["OPENAI_API_KEY"]         = ""    # Mock 강제
os.environ["VISION_CANDIDATE_RERANK"] = "false"
```

**FFmpeg 합성 영상 (18초 흑색 + 440Hz 사인파):**
```bash
ffmpeg -f lavfi -i "color=black:s=1920x1080:r=25" \
       -f lavfi -i "sine=frequency=440:sample_rate=44100" \
       -t 18 -c:v libx264 -crf 23 -c:a aac sample.mp4
```

### 8.2 추가 필요 단위 테스트

```python
# 언어 시그널 검증
def test_tone_signals_korean():
    signals = tone_signals("진짜? 말도 안 돼!")
    assert signals["question_signal"] > 0.4
    assert signals["reaction_signal"] > 0.2

# QA 스코어 경계값
def test_question_answer_score_strong():
    q = make_event(tone_signals={"question_signal": 0.7, ...})
    a = make_event(text="그래서 말이야, 내가 그랬잖아.",
                   tone_signals={"payoff_signal": 0.6, ...})
    score = question_answer_score([q, a])
    assert score > 0.45
    assert score <= 1.0

# Arc 탐색
def test_beam_search_finds_setup_payoff_arc():
    events = [
        make_event(setup_score=0.8, event_kind="question"),
        make_event(escalation_score=0.5),
        make_event(payoff_score=0.7, event_kind="payoff"),
    ]
    arcs = beam_search_arcs(events)
    assert len(arcs) > 0
    assert arcs[0].total_arc_score > 0.1

# 중복 제거
def test_iou_deduplication():
    w1 = make_window(start=10.0, end=80.0, score=8.0)  # IOU > 0.52
    w2 = make_window(start=15.0, end=75.0, score=6.0)
    result = dedupe_scored_windows([w1, w2])
    assert len(result) == 1
    assert result[0].total_score == 8.0
```

### 8.3 통합 테스트 계획

```python
# tests/test_full_pipeline.py
def test_pipeline_with_90s_video_and_srt():
    episode = create_test_episode(
        video_bytes=build_test_video_bytes(duration=90),
        subtitle_content=TEST_SRT_10_CUES,
    )
    run_analysis_pipeline_sync(episode.id)

    candidates = get_candidates(episode.id)
    assert len(candidates) >= 1
    assert all(1.0 <= c.total_score <= 10.0 for c in candidates)

    # 스코어 컴포넌트 완전성
    for c in candidates:
        for key in ["total_score", "hookability_score", "standalone_clarity_score",
                    "question_answer_score", "speech_coverage"]:
            assert key in c.scores_json, f"{key} missing"
```

### 8.4 오프라인 평가셋 및 후보 품질 평가 체계 — ✅ 완료

**목표:** 오프라인 golden set을 먼저 구축하고, 그 위에서 알고리즘을 평가.

#### 평가셋 구축 방법

```
[에피소드 샘플 5–10개]
  + 각 에피소드에 대해 사람이 직접 선별한 "좋은 후보" 3–5개
  + 각 후보에 대해:
    - 독립 이해 가능 여부 (1–5)
    - 감정 임팩트 (1–5)
    - 훅 강도 (1–5)
    - 쇼츠 길이 적합도 (1–5)
    - 전반적 품질 (1–5)
  → golden_candidates.json
```

#### 자동 평가 지표

```python
# backend/scripts/evaluate_candidates.py

def evaluate_pipeline(episode_ids: list[str], golden_set: dict) -> dict:
    """파이프라인 출력을 golden set과 비교."""
    results = {}
    for episode_id in episode_ids:
        generated = get_candidates(episode_id)
        golden = golden_set.get(episode_id, [])

        # Recall@K: golden의 몇 %를 Top-K에서 찾았는가
        recall_at_k = {
            k: _recall_at_k(generated[:k], golden)
            for k in [5, 10, 14]
        }
        # Score distribution: 전체 점수 분포
        score_stats = {
            "mean": mean(c.total_score for c in generated),
            "std": stdev(c.total_score for c in generated),
            "top3_avg": mean(c.total_score for c in generated[:3]),
        }
        results[episode_id] = {
            "recall_at_k": recall_at_k,
            "score_stats": score_stats,
            "n_composite": sum(1 for c in generated if c.metadata_json.get("composite")),
        }
    return results
```

#### 운영 워크플로우

```
스코어링 가중치 변경
  → make smoke (기능 검증)
  → python scripts/evaluate_candidates.py (품질 회귀 확인)
  → Recall@10 < 이전 값이면 롤백
```

### 8.5 성능 계측 지표 (Observability) — ✅ 완료

| 지표 | 측정 위치 | 경고 임계값 |
|------|-----------|-------------|
| `micro_event_count` | `build_micro_events()` 완료 후 | > 500개면 윈도우 탐색이 O(n²) 위험 |
| `beam_explored_states` | `beam_search_arcs()` 내 | > 50,000이면 시간 초과 위험 |
| `composite_gen_ms` | `build_composite_candidates()` 완료 후 | > 30,000ms |
| `candidate_gen_total_ms` | `generate_candidates_step()` 전체 | > 60,000ms |
| `vision_rerank_ms` | `refine_candidates_with_vision()` 완료 후 | > 120,000ms (API 레이턴시 포함) |
| `seeds_per_track` | 각 트랙 시드 생성 후 | Track A: 0이면 경고 |

---

## 9. 변경 이력 / 최근 구현 요약

### 9.1 완료된 구현 항목 (로드맵 전 단계)

| # | 항목 | 파일 | 비고 |
|---|------|------|------|
| 1 | Whisper ASR 통합 | `asr_service.py`, `analysis_service.py` | faster-whisper/openai-whisper 자동 폴백 |
| 2 | TTS 기본 구현 | `tts_service.py` | `gpt-4o-mini-tts` + silence 폴백 |
| 3 | 비디오 템플릿 렌더링 | `video_template_renderer.py` | FFmpeg ASS 기반 실제 구현 |
| 4 | Canonical Schema 고정 | `candidate_events.py` 등 | entity stop_words 필터 + serialize_event |
| 5 | 오프라인 평가셋 구축 | `scripts/evaluate_candidates.py` | Recall@K, 점수 분포, 타임라인 커버리지 |
| 6 | LLM Arc Judge | `candidate_rerank.py` | gpt-4.1-mini, 기본 비활성 |
| 7 | 오디오 에너지 프로파일 v2 | `candidate_audio_signals.py` | ebur128 단일 패스 |
| 8 | 성능 계측 삽입 | `analysis_service.py`, `candidate_generation.py` | perf dict + 경고 로그 |
| 9 | Entity·Coreference 강화 | `candidate_events.py`, `entity_service.py` | 한국어 NER + 화자 레이블 |
| 10 | Audio librosa 고급 분석 | `audio_analysis_service.py` | spectral_centroid/ZCR/MFCC + 폴백 |
| 11 | 복합 후보 3-스팬 확장 | `composite_candidate_generation.py` | setup-escalation-payoff 트리플 |
| 12 | Vision 재랭크 프롬프트 v2 | `vision_candidate_refinement.py` | 한국어 v2 + 보상/패널티 기준 명시 |
| 13 | 스코어링 가중치 A/B 프로파일 | `candidate_generation.py` | ScoringWeights (default/reaction_heavy/payoff_heavy) |
| 14 | ML 기반 언어 시그널 (임베딩) | `candidate_language_signals.py` | OpenAI embeddings + 키워드 폴백 |

### 9.2 향후 검토 (규모 확인 후)

| 항목 | 근거 |
|------|------|
| YouTube 자동 업로드 | 할당량(~6건/일)·채널 규모 확인 후. API 설계는 완료 상태 |
| Speaker Diarization (pyannote.audio) | 의존성 크므로 필요성 검증 후 도입 결정 |

### 9.3 Live Path 연결 완료 (커밋 `43b4098`)

**ML 임베딩 언어 시그널 live path 연결:**
- `score_window()` 내 `compute_embedding_signals()` 호출
- 조건: `EMBEDDING_SIGNALS_ENABLED=true` + `OPENAI_API_KEY` 존재
- 결과 혼합: `max(keyword_X, emb_X * 0.8)` 방식 (comedy/emotion/tension/reaction/payoff)
- 실패 시 keyword path 자동 폴백
- 추가 perf 항목: `embedding_signal_windows_used`, `embedding_signal_failures`

**Track C 오디오 v2 / librosa live path 연결:**
- `generate_audio_seeds_live()` 신규 함수가 Track C 단일 진입점

| 경로 | 조건 |
|------|------|
| `ebur128_v2` (기본) | 항상 시도 |
| `astats_fallback` | ebur128 결과 없을 때 자동 폴백 |
| `librosa` 보정 | `AUDIO_ANALYSIS_BACKEND=librosa/auto` 또는 `AUDIO_LIBROSA_ENABLED=true` 시 `tension_hint`/`speech_likelihood` 기반 소폭 보정 |

- ffmpeg 없거나 audio_path=None → 빈 목록 (전체 파이프라인 영향 없음)
- 추가 perf 항목: `audio_seed_backend`, `audio_seed_count`

**perf / smoke / evaluate 연결:**
- `candidate_gen_perf` dict에 임베딩·오디오 항목 추가
- smoke_test.py Tests 18–22: 임베딩 disabled/no-key 폴백, audio_path=None 생존, 시드 메타데이터 검증
- `evaluate_candidates.py`: `audio_track_candidate_count`, `embedding_used_candidate_count` 집계 추가

---

## 부록 A. 핵심 데이터 구조

### CandidateEvent

```python
@dataclass
class CandidateEvent:
    start_time: float
    end_time: float
    text: str              # 병합된 자막 텍스트
    cue_count: int
    shot_count: int
    event_kind: str        # "question"|"reaction"|"payoff"|"tension"|"emotion"|"funny_dialogue"|"dialogue"
    tone_signals: dict     # 7개 시그널 (각 0.0–1.0)
    tokens: list[str]      # 중복 제거 토큰 (Jaccard 용)
    dominant_entities: list[str]  # enhanced_dominant_entities(): 화자레이블>NER>빈도 (상위 8개)
    source_segments: list[dict]

    # 역할 점수 (candidate_role_scoring.py, 각 0.0–1.0)
    setup_score: float
    escalation_score: float
    reaction_score: float
    payoff_score: float
    standalone_score: float
    context_dependency_score: float  # 높을수록 맥락 의존적
    visual_impact_score: float
    audio_impact_score: float
```

### ScoredWindow

```python
@dataclass
class ScoredWindow:
    start_time: float
    end_time: float
    total_score: float     # [1.0, 10.0] — arc + vision 재랭크 후 최종
    scores_json: dict      # 17+ 컴포넌트 점수
    title_hint: str        # 처음 3개 자막 큐에서 추출
    metadata_json: dict    # clip_spans, source_events, entities, arc 정보
```

### clip_spans (복합 후보)

```json
[
  {
    "start_time": 1234.5, "end_time": 1264.5,
    "order": 0,
    "role": "core_setup"
  },
  {
    "start_time": 1290.0, "end_time": 1310.0,
    "order": 1,
    "role": "core_payoff"
  }
]
```

- **CORE_ROLES:** `core_setup` | `core_escalation` | `core_payoff` | `core_reaction` | `core_dialogue` | `core_followup` | `main` | `setup` | `payoff` | `reaction` | `followup` | `dialogue`
- **SUPPORT_ROLES:** `support_pre` | `support_post` | `support_bridge`

---

## 부록 B. 환경 설정 빠른 참조

```bash
# 로컬 개발 (SQLite + Celery Eager + Mock LLM)
DATABASE_URL=sqlite:///data/app.db
CELERY_TASK_ALWAYS_EAGER=true
OPENAI_API_KEY=                   # 비워두면 Mock 사용
ALLOW_MOCK_LLM_FALLBACK=true
VISION_CANDIDATE_RERANK=false
ASR_ENABLED=false                 # Whisper ASR (기본 비활성)
WHISPER_MODEL_SIZE=medium
WHISPER_PREFER_FASTER=true
DEFAULT_LANGUAGE=ko
AUDIO_ANALYSIS_BACKEND=ffmpeg     # "ffmpeg" | "librosa" | "auto"
AUDIO_LIBROSA_ENABLED=false
EMBEDDING_SIGNALS_ENABLED=false   # ML 임베딩 언어 시그널 (기본 비활성, OPENAI_API_KEY 필요)
EMBEDDING_SIGNALS_MODEL=text-embedding-3-small
EMBEDDING_SIGNALS_MAX_CHARS=1000  # 임베딩 입력 최대 문자 수
LLM_ARC_JUDGE_ENABLED=false       # gpt-4.1-mini Arc Judge (기본 비활성)
LLM_ARC_JUDGE_TOP_K=5
SCORING_PROFILE=default           # "default" | "reaction_heavy" | "payoff_heavy"

# Docker 프로덕션 (PostgreSQL + Redis + 실제 LLM)
DATABASE_URL=postgresql+psycopg://user:pass@postgres:5432/shorten
REDIS_URL=redis://redis:6379/0
CELERY_TASK_ALWAYS_EAGER=false
OPENAI_API_KEY=sk-...
VISION_CANDIDATE_RERANK=true
VISION_MAX_CANDIDATES_PER_EPISODE=8
VISION_MAX_FRAMES_PER_CANDIDATE=6
VISION_PROMPT_VERSION=vision_candidate_rerank_v2
ASR_ENABLED=true
WHISPER_MODEL_SIZE=medium
LLM_ARC_JUDGE_ENABLED=true
EMBEDDING_SIGNALS_ENABLED=true    # ML 임베딩 시그널 활성 (OPENAI_API_KEY 필수)
SCORING_PROFILE=default
FFMPEG_SCENE_THRESHOLD=0.32
PROXY_MAX_WIDTH=480
PROXY_VIDEO_FPS=6
STORAGE_ROOT=/app/storage
```

---

## 부록 C. Canonical Schema & Vocabulary (고정 인터페이스)

서비스 간 데이터 교환의 일관성을 위해 다음 값들을 사실상 인터페이스로 고정한다.
코드 변경 시 이 표를 먼저 업데이트하고 관련 서비스를 일괄 수정.

### Enum: candidate_track

```python
CANDIDATE_TRACK = Literal["dialogue", "visual", "audio"]
# dialogue: Track A — 대화 구조 기반
# visual:   Track B — 컷 밀도·반응샷 기반
# audio:    Track C — RMS 에너지 기반
```

### Enum: arc_form

```python
ARC_FORM = Literal["contiguous", "composite"]
# contiguous: 모든 인접 이벤트 간 간격 <= 12초
# composite:  하나 이상의 이벤트 간 간격 > 12초
```

### Enum: clip_span role

```python
# candidate_spans.py 기준 실제 정의
CORE_ROLES = frozenset({
    # arc beam search / composite pair에서 할당
    "core_setup",       # 아크의 설정부 이벤트 (첫 번째 이벤트)
    "core_escalation",  # 아크의 전개/고조 이벤트 (중간 이벤트)
    "core_payoff",      # 아크의 페이오프 이벤트 (마지막 이벤트)
    "core_reaction",    # 반응 이벤트
    "core_dialogue",    # 단순 대화 이벤트
    "core_followup",    # 후속 이벤트
    # 단일 스팬 / 레거시 호환
    "main",             # 단일 스팬 후보의 전체 구간 (normalize_clip_spans 기본값)
    "setup",            # 레거시 설정부
    "payoff",           # 레거시 페이오프
    "reaction",         # 레거시 반응
    "followup",         # 레거시 후속
    "dialogue",         # 레거시 대화
})
SUPPORT_ROLES = frozenset({
    "support_pre",      # 코어 앞에 패딩된 보조 구간 (3–8초)
    "support_post",     # 코어 뒤에 패딩된 보조 구간 (2–6초)
    "support_bridge",   # 두 코어 사이 연결 보조 구간 (2–5초)
})
```

### Canonical Candidate metadata_json Keys

파이프라인이 항상 채워야 하는 필수 키:

```python
REQUIRED_METADATA_KEYS = [
    "generated_by",          # str: 생성 알고리즘 버전 (예: "structure_heuristic_v2")
    "arc_form",              # ARC_FORM
    "candidate_track",       # CANDIDATE_TRACK
    "clip_spans",            # list[ClipSpan] — order 필드 포함
    "transcript_excerpt",    # str (≤ 320자)
    "dominant_entities",     # list[str] (≤ 8개)
    "dedupe_tokens",         # list[str] (≤ 16개, NMS용)
    "window_reason",         # str (예: "question_answer", "reaction_shift")
    "ranking_focus",         # str (예: "setup_payoff", "awkward_reaction")
]

# 옵션 키 (파이프라인 단계에 따라 추가)
OPTIONAL_METADATA_KEYS = [
    "source_events",         # list[SerializedCandidateEvent]
    "payoff_anchor",         # dict {start_time, end_time, payoff_score, event_kind}
    "support_added_sec",     # float
    "core_spans",            # list[ClipSpan]
    "support_spans",         # list[ClipSpan]
    "vision_rerank_applied", # bool
    "vision_score_delta",    # float
    "rerank_applied",        # bool
    "rerank_provider",       # str
    "winning_signals",       # list[str]
    "llm_arc_judge_applied", # bool
    "perf",                  # dict (성능 계측값)
    # ML 임베딩 시그널 (EMBEDDING_SIGNALS_ENABLED=true 시 채워짐)
    "embedding_used",        # bool — API 호출 성공 여부
    "embedding_attempted",   # bool — API 호출 시도 여부 (키 존재 + 플래그 활성)
    "comedy_emb",            # float (0~1)
    "emotion_emb",           # float (0~1)
    "tension_emb",           # float (0~1)
    "reaction_emb",          # float (0~1)
    "payoff_emb",            # float (0~1)
    # Track C 오디오 시드 메타데이터
    "audio_seed_backend",    # str: "ebur128_v2" | "astats_fallback" | "librosa"
    "audio_feature_backend", # str: "ffmpeg" | "librosa" | "auto"
]
```

### ClipSpan Schema

```python
class ClipSpan(TypedDict):
    start_time: float   # 에피소드 절대 시간 (초)
    end_time: float     # 에피소드 절대 시간 (초)
    order: int          # 0-based 재생 순서
    role: CLIP_SPAN_ROLE
```

### Candidate scores_json Keys (완전 목록)

```python
SCORES_KEYS = [
    # 기본 측정값 (score_window())
    "total_score",
    "speech_coverage",
    "dialogue_turn_density",   # 대화 밀도 (chars/sec 기반)
    "chars_per_sec",           # 초당 문자 수
    "cuts_inside",             # 구간 내 컷 수
    "single_arc_complete_score",  # contiguous arc 완결도 (0~1)
    # 구조 시그널
    "question_answer_score",
    "reaction_shift_score",
    "payoff_end_weight",
    "entity_consistency",
    "standalone_clarity_score",
    "hookability_score",
    # 키워드 기반 언어 시그널
    "comedy_signal",
    "emotion_signal",
    "surprise_signal",
    "tension_signal",
    "reaction_signal",
    "payoff_signal",
    # ML 임베딩 언어 시그널 (EMBEDDING_SIGNALS_ENABLED=true 시 실값, 아니면 0.0)
    "comedy_emb",
    "emotion_emb",
    "tension_emb",
    "reaction_emb",
    "payoff_emb",
    # 시각/오디오
    "visual_impact",
    "audio_impact",
    "cut_density_score",       # 재랭크 단계에서 추가
    "visual_audio_bonus",      # 재랭크 단계에서 추가
    # Arc 재랭크 (candidate_rerank.py)
    "arc_quality_delta",
    "arc_setup_strength",
    "arc_payoff_strength",
    "arc_continuity",
    # Vision 재랭크 (옵션, vision_candidate_refinement.py)
    "visual_hook_score",
    "self_contained_score",
    "emotion_shift_score",
    "thumbnail_strength_score",
]
```

---

## 부록 D. 기술 분석 상세

### D.1 프로젝트 개요

**Shorten**은 장편 드라마 에피소드를 분석하여 쇼츠(9:16 세로형) 후보 클립을 자동 생성하는 로컬-퍼스트 시스템입니다.

**핵심 목표:**
- 에피소드 영상을 업로드하면 쇼츠 후보를 자동으로 발굴
- 대사 구조, 시각적 임팩트, 오디오 에너지 등 다중 시그널로 후보 스코어링
- 선택된 후보에 대해 스크립트 초안 → 비디오 초안 → 내보내기 워크플로우 지원
- AWS 등 외부 클라우드 없이 단일 머신에서 동작

**기술 스택:**

| 계층 | 기술 |
|------|------|
| Backend | FastAPI, SQLAlchemy 2.0, Alembic, Celery 5, Redis |
| Frontend | Next.js 16 (App Router), React 19, TanStack Query |
| DB | PostgreSQL (프로덕션) / SQLite (로컬 개발·테스트) |
| 미디어 처리 | FFmpeg/FFprobe CLI |
| LLM | OpenAI SDK (mock fallback 지원) |
| 언어 | Python 3.11+, TypeScript |

---

### D.2 전체 아키텍처

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

---

### D.3 데이터베이스 스키마

**파일:** `backend/app/db/models.py`

#### Episode

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
metadata_json       JSON (분석 전 과정의 캐시·결과 저장)
created_at, updated_at
Relations: jobs, shots, transcript_segments, candidates (all cascade delete)
```

#### Shot

```
id              UUID (PK)
episode_id      FK → Episode
shot_index      int (1-based)
start_time      float (초)
end_time        float (초)
thumbnail_path  str? (JPEG 썸네일 경로)
```

#### TranscriptSegment

```
id              UUID (PK)
episode_id      FK → Episode
segment_index   int (1-based)
start_time      float
end_time        float
text            str
speaker_label   str? (미사용; entity_service.py가 텍스트의 [화자]: 패턴 파싱)
```

#### Candidate

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
scores_json      JSON (17개 이상 컴포넌트 점수)
metadata_json    JSON (clip_spans, transcript_excerpt, entities, arc 정보 등)
selected         bool
short_clip_path  str? (렌더링된 쇼츠 경로)
Relations: script_drafts, jobs, video_drafts
```

#### ScriptDraft

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
```

#### VideoDraft

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
burned_caption    bool
render_config_json JSON
timeline_json     JSON
```

#### Export

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
```

#### Job

```
id               UUID (PK)
episode_id       FK → Episode (nullable)
candidate_id     FK → Candidate (nullable)
type             Enum: ANALYSIS | SCRIPT_GENERATION | VIDEO_DRAFT_RENDER | EXPORT_RENDER | SHORT_CLIP_RENDER
status           Enum: QUEUED | RUNNING | SUCCEEDED | FAILED | CANCELLED
progress_percent int (0–100)
current_step     str
error_message    str?
payload_json     JSON
```

#### 마이그레이션 이력

| 버전 | 내용 |
|------|------|
| 0001_initial_schema | Episode, Shot, TranscriptSegment, Candidate, ScriptDraft, Job |
| 0002_video_drafts_exports | VideoDraft, Export 모델 + 상태 Enum |
| 0003_candidate_short_clip | Candidate에 short_clip_path 컬럼 추가 |
| 0004_video_draft_metadata | metadata_json 컬럼 확장 (렌더 추적) |

---

### D.4 설정 및 환경변수

**파일:** `backend/app/core/config.py`, `backend/.env.example`

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `DATABASE_URL` | `sqlite:///data/app.db` | PostgreSQL 또는 SQLite |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis URL |
| `CELERY_TASK_ALWAYS_EAGER` | `True` | True = 동기 실행 (테스트용) |
| `OPENAI_API_KEY` | `""` | 없으면 Mock 폴백 |
| `OPENAI_MODEL` | `"gpt-4.1"` | 스크립트 생성 모델 |
| `ALLOW_MOCK_LLM_FALLBACK` | `True` | OpenAI 실패 시 결정적 Mock |
| `VISION_CANDIDATE_RERANK` | `True` | GPT-4 Vision 재랭크 활성화 |
| `VISION_MAX_CANDIDATES_PER_EPISODE` | `8` | Vision 적용 최대 후보 수 |
| `VISION_MAX_FRAMES_PER_CANDIDATE` | `6` | 후보당 최대 프레임 수 |
| `VISION_MODEL` | `"gpt-4.1"` | Vision 재랭크 모델 |
| `VISION_PROMPT_VERSION` | `"vision_candidate_rerank_v2"` | 프롬프트 버전 (한국어 v2) |
| `FFMPEG_SCENE_THRESHOLD` | `0.32` | FFmpeg scene 감지 임계값 |
| `ASR_ENABLED` | `False` | Whisper ASR 활성화 |
| `WHISPER_MODEL_SIZE` | `"medium"` | Whisper 모델 크기 |
| `WHISPER_PREFER_FASTER` | `True` | faster-whisper 우선 시도 |
| `DEFAULT_LANGUAGE` | `"ko"` | ASR 기본 언어 |
| `AUDIO_ANALYSIS_BACKEND` | `"ffmpeg"` | 오디오 분석 백엔드 ("ffmpeg" \| "librosa" \| "auto") |
| `AUDIO_LIBROSA_ENABLED` | `False` | librosa 고급 분석 활성화 |
| `EMBEDDING_SIGNALS_ENABLED` | `False` | ML 임베딩 언어 시그널 (기본 비활성, OPENAI_API_KEY 필요) |
| `LLM_ARC_JUDGE_ENABLED` | `False` | LLM Arc Judge 활성화 (gpt-4.1-mini) |
| `LLM_ARC_JUDGE_TOP_K` | `5` | Arc Judge 적용 최대 후보 수 |
| `SCORING_PROFILE` | `"default"` | 스코어링 프로파일 ("default" \| "reaction_heavy" \| "payoff_heavy") |
| `PROXY_MAX_WIDTH` | `480` | 프록시 영상 최대 너비 |
| `PROXY_VIDEO_FPS` | `6` | 프록시 FPS |
| `STORAGE_ROOT` | `"./storage"` | 로컬 파일 저장 루트 |

---

### D.5 분석 파이프라인 (Celery 태스크)

**파일:** `backend/app/tasks/pipelines.py`

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

**별도 태스크 체인:**

| 체인 | 진입점 |
|------|--------|
| 스크립트 생성 | `generate_script_drafts_task` |
| 쇼츠 클립 렌더링 | `render_short_clip_task` |
| 비디오 초안 렌더링 | `render_video_draft_task` |
| 내보내기 렌더링 | `render_export_task` |

---

### D.6 분석 서비스 상세

#### Ingest Episode

- `ffprobe -show_format -show_streams` 실행
- 결과: duration, fps, width, height, has_audio 저장
- 실패 시 기본값(duration=60, fps=25, width=1920, height=1080) 사용
- `metadata_json["media_probe"]` = `{status, duration_seconds, fps, width, height}`

#### Signal Computation (`analysis_service.py`)

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

#### Transcript Branch Logic

`extract_or_generate_transcript_step()`은 세 가지 브랜치로 동작:

1. **업로드된 자막 우선:** `episode.source_subtitle_path`가 있으면 SRT/WebVTT 파싱
2. **Whisper ASR (설정 시):** `ASR_ENABLED=True`이면 `asr_service.transcribe_audio()` 호출 — faster-whisper → openai-whisper 순서로 자동 폴백
3. **없음:** 빈 segment 목록

---

### D.7 후보 생성 알고리즘 상세

#### D.7.1 세 가지 트랙

```
트랙 A: Dialogue-Driven — 자막 큐 → micro-event 분할 → 윈도우 열거 → 스코어링
트랙 B: Visual-Impact — 샷 패턴 분석 → 컷 밀도 스파이크·반응샷 패턴 감지
트랙 C: Audio-Reaction — generate_audio_seeds_live() → ebur128 기본, astats 폴백, librosa optional
```

#### D.7.2 언어 시그널 (`candidate_language_signals.py`)

**키워드 기반 ToneSignals (7개):**
```python
class ToneSignals(TypedDict):
    comedy_signal, emotion_signal, surprise_signal,
    tension_signal, reaction_signal, payoff_signal, question_signal: float  # 각 0-1
```

**임베딩 기반 EmbeddingSignals — `score_window()` live path 연결 (`EMBEDDING_SIGNALS_ENABLED` feature flag):**
```python
class EmbeddingSignals(TypedDict):
    comedy_emb, emotion_emb, tension_emb, reaction_emb, payoff_emb: float
    embedding_used: bool

def compute_embedding_signals(text, *, api_key=None, model="text-embedding-3-small") -> EmbeddingSignals:
    """OpenAI Embeddings API로 레퍼런스 앵커 문장과 코사인 유사도 계산.
    API 키 없거나 오류 시 → 키워드 기반 tone_signals로 자동 폴백.
    EMBEDDING_SIGNALS_ENABLED=true + OPENAI_API_KEY 존재 시 score_window() 내 live path 활성.
    """
```

**Entity 추출 강화 (`entity_service.py`):**
```python
def enhanced_dominant_entities(text, token_stream, *, limit=8) -> list[str]:
    """우선순위: 화자 레이블([이름]:) > 한국어 NER 패턴 > 빈도 기반 토큰."""
```

#### D.7.3 오디오 시그널 (`candidate_audio_signals.py`, `audio_analysis_service.py`)

**`generate_audio_seeds_live()` — Track C 단일 진입점 (live path 연결 완료):**

| 경로 | 조건 |
|------|------|
| `ebur128_v2` (기본) | 항상 시도; FFmpeg `ebur128` 단일 패스로 전체 에피소드 라우드니스 프로파일 추출 |
| `astats_fallback` | ebur128 결과 없을 때 자동 폴백 |
| `librosa` 보정 | `AUDIO_ANALYSIS_BACKEND=librosa/auto` 또는 `AUDIO_LIBROSA_ENABLED=true` 시 `tension_hint`/`speech_likelihood` 기반 소폭 보정 |

- ffmpeg 없거나 audio_path=None → 빈 목록 (전체 파이프라인 영향 없음)
- seed metadata: `audio_seed_backend`, `audio_profile_segment_count`, `audio_feature_backend`

**고급 오디오 분석 (`audio_analysis_service.py`):**
- librosa 백엔드: RMS, spectral_centroid(음색 밝기), ZCR(음성↔음악 구분), MFCC 13차원
- `compute_audio_emotion_scores()`: `tension_hint`(긴장도), `speech_likelihood`(음성 확률)

#### D.7.4 스코어링 — ScoringWeights A/B 프로파일

`SCORING_PROFILE` 환경변수로 선택. `ScoringWeights.from_profile(profile)` 팩토리 메서드.

| 필드 | default | reaction_heavy | payoff_heavy |
|------|---------|----------------|--------------|
| `speech_coverage` | 0.12 | 0.10 | 0.10 |
| `dialogue_density` | 0.10 | 0.08 | 0.08 |
| `qa_score` | 0.12 | 0.08 | 0.14 |
| `reaction_score` | 0.12 | 0.20 | 0.10 |
| `payoff_score` | 0.14 | 0.10 | 0.20 |
| `entity_score` | 0.06 | 0.06 | 0.06 |
| `clarity_score` | 0.10 | 0.10 | 0.10 |
| `hook_score` | 0.10 | 0.10 | 0.10 |
| `tone_signal` | 0.06 | 0.10 | 0.04 |
| `cut_density` | 0.03 | 0.03 | 0.03 |
| `visual_audio_bonus` | 0.05 | 0.05 | 0.05 |

---

### D.8 스코어링 공식 — 실제 예시 (60초 QA 패턴 후보)

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

### D.9 콘텐츠 생성 서비스

#### 스크립트 생성 (`script_service.py`)

**Mock 폴백 (`ALLOW_MOCK_LLM_FALLBACK=True`):**
```python
hook = f"이 장면이 바로 포인트입니다: {candidate.title_hint}"
body = "겉으로는 차분한데, 사실 이 대화에는..."
cta  = "{channel_style} 톤으로 더 보려면 팔로우!"
```

**estimated_duration 계산:**
```python
estimated_duration_seconds = max(15.0, len(full_script_text) / 12)
# 12 = 한국어 기준 읽기 속도 (12글자/초)
```

#### 내보내기 프리셋

| 프리셋 | 해상도 | CRF | 워터마크 |
|--------|--------|-----|---------|
| `shorts_default` | 1080×1920 | 23 | 없음 |
| `review_lowres` | 720×1280 | 30 | "INTERNAL REVIEW" |
| `archive_master` | 원본 유지 | 18 | 없음 |

---

### D.10 API 엔드포인트 전체

**Base URL:** `http://localhost:8000/api/v1`

#### Episodes

| Method | Path | 설명 |
|--------|------|------|
| `POST` | `/episodes` | 에피소드 업로드 (multipart form) |
| `GET` | `/episodes` | 목록 조회 |
| `GET` | `/episodes/{id}` | 상세 조회 |
| `DELETE` | `/episodes/{id}` | 삭제 (파일 + DB) |
| `GET` | `/episodes/{id}/source-video` | 원본 영상 스트리밍 |
| `POST` | `/episodes/{id}/analyze` | 분석 시작 |
| `POST` | `/episodes/{id}/clear-analysis` | 후보·초안·내보내기 전체 삭제 |
| `POST` | `/episodes/{id}/clear-cache` | 프록시·오디오·썸네일·Vision 캐시 삭제 |
| `GET` | `/episodes/{id}/timeline` | shots + transcript segments 반환 |
| `GET` | `/episodes/{id}/jobs` | 에피소드 작업 목록 |
| `GET` | `/episodes/{id}/candidates` | 후보 목록 (status?, min_score?, type?, sort_by?) |

#### Candidates & Drafts

| Method | Path | 설명 |
|--------|------|------|
| `GET` | `/candidates/{id}` | 후보 상세 |
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

#### Jobs

| Method | Path | 설명 |
|--------|------|------|
| `GET` | `/jobs` | 작업 목록 (episode_id?, candidate_id?, type?, status?) |
| `GET` | `/jobs/{id}` | 작업 상세 |

---

### D.11 프론트엔드 구조

**스택:** Next.js 16 App Router + React 19 + TanStack Query v5 + TypeScript

#### 페이지 구조

```
/                          → /episodes 리다이렉트
/episodes                  → 에피소드 목록
/episodes/new              → 업로드 폼
/episodes/[episodeId]      → 에피소드 상세 + 타임라인 + 작업 진행 상태
/episodes/[episodeId]/candidates → 후보 목록 + 필터
/candidates/[candidateId]  → 후보 상세 (점수, 스팬, 트랜스크립트)
/drafts/[draftId]          → 비디오 초안 편집기
/exports/[exportId]        → 내보내기 다운로드
```

#### 데이터 페칭 패턴

```typescript
// Client Component (실시간 폴링 — JobsLive)
const { data: jobs } = useQuery({
  queryKey: ["jobs", episodeId],
  queryFn: () => getJobs({ episode_id: episodeId }),
  refetchInterval: 2000,  // 2초마다 폴링
  staleTime: 0,
});
```

---

### D.12 스모크 테스트

**파일:** `backend/scripts/smoke_test.py`

```bash
ffmpeg -f lavfi -i "color=black:s=1920x1080:r=25" \
       -f lavfi -i "sine=frequency=440:sample_rate=44100" \
       -t 18 -c:v libx264 -crf 23 -c:a aac -b:a 128k sample.mp4
```

테스트 시퀀스: 단위 테스트(tone signals, QA 패턴, IOU 중복 제거) → 통합 테스트(POST /episodes ~ GET /exports/{id}) → 임베딩 disabled/no-key 폴백 검증(Tests 18–22) → audio_path=None 생존 검증.

---

### D.13 스토리지 레이아웃

```
backend/storage/
└── episodes/
    └── {episode_id}/
        ├── source/
        │   ├── source.mp4
        │   └── source.srt
        ├── proxy/
        │   └── analysis_proxy.mp4  (480p, 6fps)
        ├── audio/
        │   └── analysis_audio.m4a  (64k AAC)
        ├── shots/
        │   ├── 0001.jpg
        │   └── {shot_index:04d}/
        │       ├── frame_001.jpg
        │       └── frame_006.jpg
        ├── candidates/
        │   └── {candidate_id}/
        │       ├── video_drafts/1/draft.mp4
        │       └── short_clip_1.mp4
        └── cache/
            ├── vision_rerank.json
            └── shots_cache.json
```

---

### D.14 메타데이터 JSON 구조

#### Episode.metadata_json

```json
{
  "media_probe": {"status": "ok", "duration_seconds": 2580.0, "fps": 25.0, "width": 1920, "height": 1080},
  "proxy_transcode": {"version": "proxy_v2", "status": "completed", "mode": "analysis_proxy"},
  "shot_detection": {"mode": "ffmpeg_scene", "status": "completed", "shot_count": 87, "cache_key": "abc123"},
  "vision_scan": {"status": "completed", "frame_count": 522, "shots_with_keyframes": 87, "version": "vision_scan_v1"},
  "transcript_source": "uploaded_subtitle",
  "signals": {"algorithm": "signals_v1", "transcript_segment_count": 1240, "estimated_speech_timeline_ratio": 0.68, "commentary_friendly": true}
}
```

#### Candidate.metadata_json (주요 필드)

```json
{
  "generated_by": "structure_heuristic_v2",
  "arc_form": "contiguous",
  "candidate_track": "dialogue",
  "window_reason": "question_answer",
  "transcript_excerpt": "왜 그런 거야?... 그래서 말이야...",
  "dominant_entities": ["주인공", "상대역"],
  "clip_spans": [{"start_time": 1234.5, "end_time": 1294.5, "order": 0, "role": "main"}],
  "vision_rerank_applied": true,
  "vision_score_delta": 0.8,
  "rerank_applied": true,
  "winning_signals": ["strong_payoff", "payoff_exceeds_setup"]
}
```

---

### D.15 한계 및 구현 완료 항목

#### 구현 완료 항목 (로드맵 1~3단계 + Live Path)

| 기능 | 상태 | 파일 |
|------|------|------|
| TTS 렌더링 | **구현됨** — OpenAI `gpt-4o-mini-tts`, silence 폴백 | `tts_service.py` |
| 비디오 편집 템플릿 | **구현됨** — FFmpeg ASS 자막 번인·텍스트 슬롯·TTS | `video_template_renderer.py` |
| ASR (음성→텍스트) | **구현됨** — faster-whisper/openai-whisper, 자동 폴백 | `asr_service.py` |
| LLM Arc 판정 | **구현됨** — gpt-4.1-mini, `LLM_ARC_JUDGE_ENABLED=True` 시 동작 | `candidate_rerank.py` |
| 오디오 고급 분석 | **구현됨** — ebur128 단일 패스 + librosa optional | `candidate_audio_signals.py`, `audio_analysis_service.py` |
| Entity·Coreference | **구현됨** — 화자 레이블 + 한국어 NER + _PRONOUN_STOP 필터 | `entity_service.py`, `candidate_language_signals.py` |
| 후보 품질 평가 체계 | **구현됨** — Recall@K, 점수 분포, 타임라인 커버리지 | `scripts/evaluate_candidates.py` |
| 성능 계측 | **구현됨** — perf dict in `episode.metadata_json["candidate_gen_perf"]` | `analysis_service.py` |
| 복합 후보 3-스팬 | **구현됨** — setup-escalation-payoff 트리플, 최대 90초 | `composite_candidate_generation.py` |
| Vision 프롬프트 v2 | **구현됨** — 한국어 v2, 보상/패널티 기준 명시 | `vision_candidate_refinement.py` |
| 스코어링 A/B 프로파일 | **구현됨** — ScoringWeights (default/reaction_heavy/payoff_heavy) | `candidate_generation.py` |
| ML 언어 시그널 | **구현됨** — OpenAI embeddings 코사인 유사도 + 키워드 폴백; `score_window()` live path 연결 (`EMBEDDING_SIGNALS_ENABLED` feature flag) | `candidate_language_signals.py` |
| 오디오 Track C live path | **구현됨** — `generate_audio_seeds_live()` Track C 진입점; ebur128 기본, astats 폴백, librosa optional | `candidate_audio_signals.py` |

#### 설계 제약

| 제약 | 값/조건 |
|------|--------|
| 최대 후보 수 (에피소드당) | 14개 (MAX_CANDIDATES) |
| Vision 적용 최대 후보 수 | 8개 (VISION_MAX_CANDIDATES_PER_EPISODE) |
| LLM Arc Judge 적용 최대 | 5개 (LLM_ARC_JUDGE_TOP_K) |
| 윈도우 길이 범위 | 30–180초 |
| 최대 샷 수 | 100개 (MAX_SHOTS) |
| 2-span 복합 최대 합산 길이 | 64초 (MAX_TOTAL_DURATION_SEC) |
| 3-span 복합 최대 합산 길이 | 90초 (MAX_TRIPLE_DURATION_SEC) |
| 세그먼트 간 유효 간격 | 6–420초 |
| micro_event 수 경고 임계값 | > 500개 |
| composite_gen_ms 경고 | > 30,000ms |
| vision_rerank_ms 경고 | > 120,000ms |

#### MVP 외 범위 (의도적 제외)

- **멀티유저·권한 관리 고도화** — 단일 운영자 시스템으로 충분
- **저작권 감지** — 내부 편집 보조 도구 범위를 벗어남
- **실시간 협업** — 현재 운영 규모에서 불필요
- **완전 무인 자동 배포** — 사람의 검수가 필수
- **YouTube/SNS 자동 업로드** — 타당성 조사 후 결정 (할당량 제한: ~6건/일)

#### 코드 내 주요 주석

- `config.py`: `CANDIDATE_RERANK_LLM` 레거시 플래그 — `VISION_CANDIDATE_RERANK=True` 또는 이 플래그 중 하나만 켜도 Vision 재랭크 활성화 (`vision_rerank_enabled` 프로퍼티)
- `candidate_rerank.py`: `llm_arc_judge()`는 실제 구현됨. `LLM_ARC_JUDGE_ENABLED=False`(기본값)이면 조용히 스킵
- `asr_service.py`: `ASR_ENABLED=False`(기본값). 활성화 시 faster-whisper → openai-whisper 순 폴백

---

*작성 기준: 2026-03-31 / 본문 기준 커밋 `93bf630`*
