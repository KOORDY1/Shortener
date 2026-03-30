# 쇼츠 후보 자동 생성 파이프라인 상세 계획

> 장편 드라마 에피소드(또는 영화)를 분석해 9:16 세로형 쇼츠 후보 클립을 자동 생성하는 시스템의 전체 설계 및 구현 계획.
> 실제 코드베이스(`backend/app/services/`, `backend/app/tasks/`) 기반으로 작성.

---

## 목차

1. [현재 구현 상태 진단](#1-현재-구현-상태-진단)
2. [전체 파이프라인 설계](#2-전체-파이프라인-설계)
3. [Phase 1 — 분석 파이프라인](#3-phase-1--분석-파이프라인)
4. [Phase 2 — 후보 생성 엔진](#4-phase-2--후보-생성-엔진)
5. [Phase 3 — 스코어링 시스템 상세](#5-phase-3--스코어링-시스템-상세)
6. [Phase 4 — Vision·LLM 정제](#6-phase-4--visionllm-정제)
7. [Phase 5 — 렌더링 파이프라인 완성](#7-phase-5--렌더링-파이프라인-완성)
8. [미구현 항목 구체적 구현 계획](#8-미구현-항목-구체적-구현-계획)
9. [테스트 전략](#9-테스트-전략)
10. [우선순위 로드맵](#10-우선순위-로드맵)
11. [Live Path 연결 구현 결과](#11-live-path-연결-구현-결과)

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
| YouTube/SNS 자동 업로드 | 타당성 조사 후 결정 (Section 8.7 참조) |
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

**현재 한계:** SRT/WebVTT 업로드 파일만 지원. ASR 통합 계획은 Section 8.1 참조.

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

#### ML 기반 임베딩 시그널 (신규)

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

## 8. 미구현 항목 구체적 구현 계획

### 8.1 ASR 통합 (Whisper) — ✅ 완료

**목적:** SRT 파일 없이도 분석 파이프라인 실행 가능.

```python
# 새 파일: backend/app/services/asr_service.py
import whisper

def transcribe_with_whisper(
    audio_path: Path,
    *,
    model_size: str = "medium",
    language: str = "ko",
    initial_prompt: str = "",   # 도메인 힌트 ("드라마 대사" 등)
) -> list[SubtitleCue]:
    model = whisper.load_model(model_size)
    result = model.transcribe(
        str(audio_path),
        language=language,
        initial_prompt=initial_prompt,
        word_timestamps=True,
        condition_on_previous_text=False,  # 드라마에서 더 안정적
        compression_ratio_threshold=2.2,
        no_speech_threshold=0.6,
    )
    return [
        SubtitleCue(start=seg["start"], end=seg["end"], text=seg["text"].strip())
        for seg in result["segments"]
    ]
```

**`extract_or_generate_transcript_step()` 수정 포인트 (`analysis_service.py`):**

```python
def extract_or_generate_transcript_step(db, payload):
    episode = db.get(Episode, payload["episode_id"])

    if episode.source_subtitle_path:
        cues = parse_subtitle_file(episode.source_subtitle_path)
        source = "uploaded_subtitle"
    elif settings.asr_enabled:   # 새 설정값
        from app.services.asr_service import transcribe_with_whisper
        audio_path = resolve_audio_path(episode)
        cues = transcribe_with_whisper(
            audio_path,
            model_size=settings.whisper_model_size,
            language=settings.default_language,
        )
        source = f"whisper_{settings.whisper_model_size}"
    else:
        cues = []
        source = "none"

    _save_transcript_segments(db, episode.id, cues)
    episode.metadata_json = {**episode.metadata_json, "transcript_source": source}
```

**추가할 설정값 (`core/config.py`):**
```python
asr_enabled: bool = False
whisper_model_size: str = "medium"   # tiny/base/small/medium/large
default_language: str = "ko"
```

**성능 기준:**
- `medium` 모델: 45분 에피소드 약 5–8분 (CPU), 1–2분 (GPU)
- `faster-whisper` 라이브러리 사용 시 2–4× 가속 가능
- ASR 결과 캐싱: `metadata_json["asr_cache_key"]` = 오디오 파일 서명

---

### 8.2 LLM Arc Judge 구현 — ✅ 완료

```python
# candidate_rerank.py - llm_arc_judge() 실제 구현
ARC_JUDGE_SYSTEM_PROMPT = """
당신은 한국 드라마 쇼츠 편집 전문가입니다.
클립 후보의 대사 발췌문을 읽고 JSON으로 평가하세요.

반환 형식:
{
  "arc_closed": bool,      // setup→payoff 명확히 닫히는가?
  "standalone": 0-10,      // 앞뒤 맥락 없이 이해 가능한가?
  "shorts_fit": 0-10,      // 30~75초 쇼츠로 적합한가?
  "adjustment": -1.0~1.0,  // 점수 조정값
  "reason": "..."          // 한국어 판단 이유 (최대 120자)
}
"""

def llm_arc_judge(windows, *, top_k=5, provider="openai"):
    client = OpenAI(api_key=settings.openai_api_key)

    for i, window in enumerate(windows[:top_k]):
        excerpt = window.metadata_json.get("transcript_excerpt", "")
        context = {
            "title_hint": window.title_hint,
            "duration_sec": window.end_time - window.start_time,
            "heuristic_score": window.total_score,
            "window_reason": window.metadata_json.get("window_reason"),
            "transcript_excerpt": excerpt[:600],
        }
        response = client.chat.completions.create(
            model="gpt-4.1-mini",   # 비용 효율적
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": ARC_JUDGE_SYSTEM_PROMPT},
                {"role": "user",   "content": json.dumps(context, ensure_ascii=False)},
            ],
            temperature=0.1, max_tokens=300,
        )
        payload = json.loads(response.choices[0].message.content)
        delta = clamp(float(payload.get("adjustment", 0.0)), -1.0, 1.0)
        windows[i] = _apply_llm_adjustment(windows[i], delta, payload)

    return windows
```

---

### 8.3 TTS 렌더링 — ✅ 구현 완료

```python
# backend/app/services/tts_service.py (실제 구현 기준)

def synthesize_short_tts(
    *,
    text: str,
    output_path: Path,
    voice_key: str | None,      # "alloy" | "echo" | "fable" | "onyx" | "nova" | "shimmer"
    duration_sec: float,
) -> TTSResult:
    """OpenAI gpt-4o-mini-tts 호출. API 키 없거나 실패 시 FFmpeg silence 폴백."""
    if text and settings.openai_api_key:
        response = httpx.post(
            "https://api.openai.com/v1/audio/speech",
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            json={"model": "gpt-4o-mini-tts", "voice": voice_key, "input": text, "format": "mp3"},
            timeout=120.0,
        )
        response.raise_for_status()
        output_path.write_bytes(response.content)
        # duration_sec 기준으로 apad/atrim 정규화 후 반환
        ...
    else:
        # silence 폴백: ffmpeg -f lavfi -i anullsrc -t {duration_sec} -c:a aac
        _ffmpeg_silence(output_path.with_suffix(".m4a"), duration_sec)
```

**비디오 템플릿 렌더러 기본 구현 (`video_template_renderer.py`):**

```python
def render_video_draft_assets(db, video_draft, *, render_config):
    candidate = db.get(Candidate, video_draft.candidate_id)
    script_draft = db.get(ScriptDraft, video_draft.script_draft_id)
    out_dir = build_out_dir(candidate, video_draft.version_no)

    # 1. TTS 오디오 생성
    tts_audio_path = None
    if video_draft.tts_voice_key and script_draft:
        tts_audio_path = out_dir / "tts_narration.mp3"
        generate_tts_audio(
            script_draft.full_script_text,
            voice_key=video_draft.tts_voice_key,
            output_path=tts_audio_path,
        )

    # 2. clip_spans 기반 원본 클립 추출
    clip_spans = candidate.metadata_json.get("clip_spans", [])
    raw_clip_path = _extract_clip_spans(candidate, clip_spans, out_dir)

    # 3. 세로형 변환 + 자막 + TTS 믹스
    draft_video_path = out_dir / "draft.mp4"
    _build_vertical_video(
        src=raw_clip_path,
        tts_audio=tts_audio_path,
        output=draft_video_path,
        width=video_draft.width,       # 1080
        height=video_draft.height,     # 1920
        burned_caption=video_draft.burned_caption,
        script_draft=script_draft,
    )
    return {"draft_video_path": str(draft_video_path), ...}
```

---

### 8.4 Audio Track 운영 수준 구현 — ✅ 완료

현재 오디오 시그널은 FFmpeg astats 기반 RMS 에너지만 측정한다. 실제 운영 품질을 위해서는 두 가지가 필요하다.

#### 8.4-A. 성능 최적화 (단일 FFmpeg 호출) — ✅ 완료

`extract_audio_energy_profile_v2()` 구현. ebur128 단일 패스. astats 폴백 포함.

```python
def extract_audio_energy_profile_v2(audio_path: Path, duration_seconds: float) -> list[dict]:
    """단일 FFmpeg 호출로 전체 ebur128 라우드니스 프로파일 추출."""
    proc = subprocess.run([
        "ffmpeg", "-i", str(audio_path),
        "-af", "ebur128=framelog=verbose",
        "-f", "null", "-",
    ], capture_output=True, text=True, timeout=300)
    # 출력 파싱: "t: 5.00 M: -18.2 S: -20.1 I: -23.0"
    return _parse_ebur128_output(proc.stderr)
```

단일 호출로 처리 시간 1/100 이하 단축 가능.

#### 8.4-B. 감정·음색 기반 오디오 분석 (운영 수준) — ✅ 완료

`audio_analysis_service.py`로 구현. librosa optional dependency.

**목표 시그널:**
- `audio_emotion_score`: 화남/슬픔/기쁨 등 감정 강도 (0–1)
- `speech_energy_burst`: 목소리 에너지 급등 (현재 silence_to_spike 개선)
- `music_presence`: BGM 존재 여부 (0–1) — 음악 있으면 감동 씬 가능성↑
- `laughter_score`: 웃음소리 감지 (0–1) — comedy 후보 강화

**구현 방향:**
```python
# 새 파일: backend/app/services/audio_analysis_service.py
# librosa 또는 pyannote.audio 활용

import librosa
import numpy as np

def extract_audio_features(audio_path: Path, segment_length: float = 5.0) -> list[dict]:
    """librosa 기반 고급 오디오 특징 추출."""
    y, sr = librosa.load(str(audio_path), sr=16000, mono=True)

    segments = []
    hop = int(segment_length * sr)
    for i, start_sample in enumerate(range(0, len(y), hop)):
        chunk = y[start_sample : start_sample + hop]
        if len(chunk) < sr: continue  # 1초 미만 스킵

        # 에너지 (RMS)
        rms = float(np.sqrt(np.mean(chunk**2)))

        # Spectral centroid (음색 밝기: 높으면 흥분/긴장)
        centroid = float(np.mean(librosa.feature.spectral_centroid(y=chunk, sr=sr)))

        # Zero-crossing rate (음성 vs 음악 구분)
        zcr = float(np.mean(librosa.feature.zero_crossing_rate(chunk)))

        # MFCCs (감정 분류 입력)
        mfcc = librosa.feature.mfcc(y=chunk, sr=sr, n_mfcc=13)
        mfcc_mean = mfcc.mean(axis=1).tolist()

        segments.append({
            "start": round(i * segment_length, 3),
            "end": round((i + 1) * segment_length, 3),
            "rms": round(rms, 4),
            "spectral_centroid": round(centroid, 1),
            "zcr": round(zcr, 4),
            "mfcc_mean": mfcc_mean,
        })
    return segments
```

**설정값 추가 (`core/config.py`):**
```python
audio_analysis_backend: str = "ffmpeg"  # "ffmpeg" | "librosa"
audio_librosa_enabled: bool = False      # librosa 활성화 (의존성 추가 필요)
```

**의존성 추가 (`pyproject.toml`):**
```toml
# [project.optional-dependencies]
audio = ["librosa>=0.10", "soundfile>=0.12"]
```

---

### 8.5 Entity·Coreference·Speaker Continuity 강화 — ✅ 완료

**현재 한계:**
- `dominant_entities`는 단순 토큰 빈도 기반 (고유명사 vs 일반명사 구분 없음)
- "그", "she", "그녀" 등 대명사가 entity로 오인되거나 entity_consistency를 낮춤
- speaker 정보(누가 말하는지)가 TranscriptSegment에 없음

**목표:**
1. **NER (Named Entity Recognition):** 인물명·장소명 고신뢰도 추출
2. **Coreference 해소:** "그" → "이준혁" 등 지시어 해소
3. **Speaker Diarization:** 화자 분리 → speaker_label 채우기

**구현 방향:**

```python
# 새 파일: backend/app/services/entity_service.py

# 방법 A: 규칙 기반 (빠름, 한국어 인물명 패턴)
def extract_named_entities_rule_based(text: str) -> list[str]:
    """한국어 인물명 패턴: 2–4글자 + 직함/호칭 패턴."""
    patterns = [
        r"[가-힣]{2,4}씨",      # "이준혁씨"
        r"[가-힣]{2,4}(대리|과장|팀장|사장|선생|교수)",
        r"[A-Z][a-z]+(?:\s[A-Z][a-z]+)?",  # 영문 인물명
    ]
    entities = []
    for pat in patterns:
        entities.extend(re.findall(pat, text))
    return list(dict.fromkeys(entities))  # 중복 제거, 순서 유지

# 방법 B: 모델 기반 (정확함, 의존성 큼)
# from transformers import pipeline
# ner_pipeline = pipeline("ner", model="snunlp/KR-FinBert-SC")

# Speaker diarization (pyannote.audio)
# from pyannote.audio import Pipeline
# diarization = Pipeline.from_pretrained("pyannote/speaker-diarization")
```

**단기 접근법 (의존성 최소):**
- `dominant_entities` 추출 시 stop_words(대명사, 조사 부착 형태) 필터링 강화
- speaker_label은 자막 파일에서 `[이름]:` 패턴이 있으면 파싱
- coreference는 단순 window 내 마지막 언급 인물명으로 대리

**`candidate_events.py` 수정 포인트:**
```python
# build_micro_events() 내부 entity 추출 개선
def _extract_dominant_entities(text: str) -> list[str]:
    tokens = tokenize(text)
    # 현재: 모든 토큰 빈도 기반
    # 개선: stop_words 필터 + 고유명사 패턴 우선
    PRONOUN_STOP = {"그", "그녀", "그들", "저", "나", "너", "이", "저기",
                    "he", "she", "they", "it", "we", "you", "i"}
    candidates = [t for t in tokens if t not in PRONOUN_STOP and len(t) >= 2]
    return Counter(candidates).most_common(8)
```

---

### 8.6 YouTube 자동 업로드 타당성 조사 — 🟢 낮음

**질문:** YouTube Data API v3를 통한 자동 업로드가 실용적으로 가능한가?

**현황 정리:**

| 항목 | 내용 |
|------|------|
| API | YouTube Data API v3 (`videos.insert`) |
| 인증 | OAuth 2.0 (채널 소유자 계정 연결 필요) |
| 할당량 | 기본 10,000 유닛/일; `videos.insert` = 1,600 유닛/요청 → **하루 약 6개 업로드** |
| 할당량 확장 | 심사 신청 가능하나 승인 불확실 |
| 제약 | 계정당 연결 제한; 다중 채널 운영 시 채널별 OAuth 토큰 관리 필요 |

**결론 (현 시점):**
- 할당량 제한(6개/일)이 운영 규모에 따라 병목이 될 수 있음
- 단일 채널 소량 업로드라면 충분
- 다계정·자동화 대량 업로드는 API 정책 위반 위험
- **MVP에서는 제외. 운영 규모 확인 후 3단계에서 재검토.**

**향후 구현 시 필요한 것:**
```python
# backend/app/services/youtube_upload_service.py (향후)
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

def upload_to_youtube(
    video_path: Path,
    *,
    title: str,
    description: str,
    tags: list[str],
    credentials,  # OAuth2Credentials
    privacy_status: str = "private",  # 초기에는 private으로 올리고 검수 후 public
) -> str:  # → video_id
    youtube = build("youtube", "v3", credentials=credentials)
    body = {
        "snippet": {"title": title, "description": description, "tags": tags},
        "status": {"privacyStatus": privacy_status},
    }
    media = MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True)
    request = youtube.videos().insert(part=",".join(body.keys()), body=body, media_body=media)
    response = request.execute()
    return response["id"]
```

---

## 9. 테스트 전략

### 9.1 기존 스모크 테스트 (`backend/scripts/smoke_test.py`)

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

### 9.2 추가 필요 단위 테스트

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

### 9.3 통합 테스트 계획

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

### 9.4 오프라인 평가셋 및 후보 품질 평가 체계 — ✅ 완료

**현재 문제:** 후보 품질을 측정하는 객관적 기준이 없음. 스코어링 가중치를 바꿔도 결과가 좋아졌는지 알 수 없음.

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
# 새 파일: backend/scripts/evaluate_candidates.py

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
        # Time coverage: 에피소드 전체 구간 중 커버된 비율
        coverage = _timeline_coverage(generated)

        results[episode_id] = {
            "recall_at_k": recall_at_k,
            "score_stats": score_stats,
            "coverage": coverage,
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

**우선순위:** 실제 에피소드 1개 + 사람 레이블 3세트면 시작 가능. 초기 투자 대비 효과 높음.

---

### 9.5 성능 계측 지표 (Observability) — ✅ 완료

후보 생성 파이프라인의 탐색량·처리 시간을 계측해 병목을 파악해야 한다. 특히 긴 영화(90분+)에서 허용 가능한지 확인 필요.

#### 계측 대상 지표

| 지표 | 측정 위치 | 경고 임계값 |
|------|-----------|-------------|
| `micro_event_count` | `build_micro_events()` 완료 후 | > 500개면 윈도우 탐색이 O(n²) 위험 |
| `beam_explored_states` | `beam_search_arcs()` 내 | > 50,000이면 시간 초과 위험 |
| `composite_gen_ms` | `build_composite_candidates()` 완료 후 | > 30,000ms |
| `candidate_gen_total_ms` | `generate_candidates_step()` 전체 | > 60,000ms |
| `vision_rerank_ms` | `refine_candidates_with_vision()` 완료 후 | > 120,000ms (API 레이턴시 포함) |
| `seeds_per_track` | 각 트랙 시드 생성 후 | Track A: 0이면 경고 |

#### 구현 방법 (Job 메타데이터 활용)

```python
# analysis_service.py - generate_candidates_step() 수정 포인트
import time

def generate_candidates_step(db, payload):
    episode_id = payload["episode_id"]
    perf = {}

    t0 = time.perf_counter()
    events = build_micro_events(segments, shots)
    perf["micro_event_count"] = len(events)
    perf["micro_event_build_ms"] = int((time.perf_counter() - t0) * 1000)

    t0 = time.perf_counter()
    arcs = beam_search_arcs(events)
    perf["beam_explored_states"] = _beam_state_count  # 전역 카운터
    perf["beam_search_ms"] = int((time.perf_counter() - t0) * 1000)

    t0 = time.perf_counter()
    composites = build_composite_candidates(all_seeds, events, timeline_end)
    perf["composite_gen_ms"] = int((time.perf_counter() - t0) * 1000)

    # Job.payload_json에 성능 지표 저장
    job.payload_json = {**job.payload_json, "perf": perf}

    # 경고 로깅
    if perf["micro_event_count"] > 500:
        logger.warning(f"[{episode_id}] micro_event_count={perf['micro_event_count']} > 500")
    if perf["beam_explored_states"] > 50_000:
        logger.warning(f"[{episode_id}] beam_explored_states={perf['beam_explored_states']}")
```

---

## 10. 우선순위 로드맵

### 즉시 착수 — 핵심 기능 완성

| # | 작업 | 파일 | 근거 |
|---|------|------|------|
| 1 | ~~Whisper ASR 통합~~ | `asr_service.py` (신규), `analysis_service.py` | **완료** — faster-whisper/openai-whisper 자동 폴백 |
| 2 | ~~TTS 기본 구현 (OpenAI TTS)~~ | `tts_service.py` | **완료** — `gpt-4o-mini-tts` 실제 구현 |
| 3 | ~~비디오 템플릿 렌더링 기본 구현~~ | `video_template_renderer.py` | **완료** — FFmpeg ASS 기반 실제 구현 |
| 4 | ~~Canonical Schema 고정~~ | `candidate_events.py` 등 | **완료** — entity stop_words 필터 + serialize_event 완전성 |
| 5 | ~~오프라인 평가셋 구축~~ | `scripts/evaluate_candidates.py` (신규) | **완료** — Recall@K, 점수 분포, 타임라인 커버리지 |

### 2단계 — 품질 개선

| # | 작업 | 파일 | 근거 |
|---|------|------|------|
| 6 | ~~LLM Arc Judge 구현~~ | `candidate_rerank.py` | **완료** — gpt-4.1-mini 기반 서사 품질 필터링 |
| 7 | ~~오디오 에너지 프로파일 v2 (단일 FFmpeg)~~ | `candidate_audio_signals.py` | **완료** — ebur128 단일 패스 |
| 8 | ~~성능 계측 삽입~~ | `analysis_service.py`, `candidate_generation.py` | **완료** — perf dict + 경고 로그 |
| 9 | ~~Entity·Coreference 강화~~ | `candidate_events.py`, `entity_service.py` (신규) | **완료** — 한국어 NER + 화자 레이블 |
| 10 | ~~Audio librosa 고급 분석~~ | `audio_analysis_service.py` (신규) | **완료** — spectral_centroid/ZCR/MFCC + 폴백 |
| 11 | ~~복합 후보 3-스팬 확장~~ | `composite_candidate_generation.py` | **완료** — setup-escalation-payoff 트리플 |

### 3단계 — 운영 강화

| # | 작업 | 파일 | 근거 |
|---|------|------|------|
| 12 | ~~Vision 재랭크 프롬프트 개선~~ | `vision_candidate_refinement.py` | **완료** — 한국어 v2 프롬프트 + 보상/패널티 기준 명시 |
| 13 | ~~스코어링 가중치 A/B 테스트 (평가셋 기반)~~ | `candidate_generation.py` | **완료** — ScoringWeights 프로파일 (default/reaction_heavy/payoff_heavy) |
| 14 | ~~ML 기반 언어 시그널 (임베딩)~~ | `candidate_language_signals.py` | **완료** — OpenAI embeddings + 키워드 폴백 |

### 4단계 — 향후 검토 (규모 확인 후)

| # | 작업 | 근거 |
|---|------|------|
| 15 | YouTube 자동 업로드 | 할당량·채널 규모 확인 후 (Section 8.6) |
| 16 | Speaker Diarization (pyannote.audio) | 의존성 크므로 필요성 검증 후 |

### 5단계 — Live Path 연결 ✅ 완료

| # | 작업 | 파일 | 근거 |
|---|------|------|------|
| 17 | ~~ML 임베딩 시그널 → `score_window()` live path 연결~~ | `candidate_generation.py`, `candidate_language_signals.py`, `config.py` | **완료** — `EMBEDDING_SIGNALS_ENABLED` feature flag, 기본 비활성 |
| 18 | ~~Track C → `generate_audio_seeds_v2()` 승격 + optional librosa 보정~~ | `candidate_generation.py`, `candidate_audio_signals.py`, `audio_analysis_service.py` | **완료** — `generate_audio_seeds_live()` wrapper, ebur128 기본·librosa optional |
| 19 | ~~perf / smoke / evaluate에 두 항목 흔적 연결~~ | `analysis_service.py`, `smoke_test.py`, `evaluate_candidates.py` | **완료** — Tests 18-22, perf dict 항목, evaluate 집계 추가 |

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

## 11. Live Path 연결 구현 결과 ✅ 완료

> 헬퍼로만 존재하던 두 기능을 실제 후보 생성 품질에 영향을 주는 live path로 승격 완료.

### 11.1 ML 임베딩 언어 시그널 ✅

**구현 파일**: `candidate_generation.py`, `candidate_language_signals.py`, `config.py`

`score_window()` 내에서 후보 window 당 1회 `compute_embedding_signals()` 호출.
- 조건: `EMBEDDING_SIGNALS_ENABLED=true` + `OPENAI_API_KEY` 존재
- 결과 혼합: `max(keyword_X, emb_X * 0.8)` 방식으로 comedy/emotion/tension/reaction/payoff 보조 합성
- 실패·미설정 시: 기존 keyword path로 자동 폴백 (전체 파이프라인 영향 없음)
- 추가된 metadata: `embedding_used`, `embedding_attempted`, `comedy_emb`~`payoff_emb`
- 추가된 perf 항목: `embedding_signal_windows_used`, `embedding_signal_failures`

---

### 11.2 Track C 오디오 v2 / librosa Live Path ✅

**구현 파일**: `candidate_audio_signals.py`, `candidate_generation.py`, `config.py`

`generate_audio_seeds_live()` 신규 함수가 Track C 단일 진입점.

| 경로 | 조건 |
|------|------|
| `ebur128_v2` (기본) | 항상 시도 |
| `astats_fallback` | ebur128 결과 없을 때 자동 폴백 |
| `librosa` 보정 | `AUDIO_ANALYSIS_BACKEND=librosa/auto` 또는 `AUDIO_LIBROSA_ENABLED=true` 시 `tension_hint`/`speech_likelihood` 기반 소폭 보정 |

- ffmpeg 없거나 audio_path=None → 빈 목록 (전체 파이프라인 영향 없음)
- 추가된 seed metadata: `audio_seed_backend`, `audio_profile_segment_count`, `audio_feature_backend`
- 추가된 perf 항목: `audio_seed_backend`, `audio_seed_count`

---

### 11.3 perf / smoke / evaluate 연결 ✅

**구현 파일**: `analysis_service.py`, `smoke_test.py`, `evaluate_candidates.py`

- `candidate_gen_perf` dict에 4개 항목 추가 (§11.1 perf + §11.2 perf)
- smoke_test.py Tests 18–22: 임베딩 disabled/no-key 폴백, audio_path=None 생존, 시드 메타데이터 검증
- `evaluate_candidates.py`: `audio_track_candidate_count`, `embedding_used_candidate_count` 집계 추가

---

*작성 기준: 2026-03-31 / 본문 기준 커밋 `ea32334`*
