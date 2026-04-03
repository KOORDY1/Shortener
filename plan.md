# 쇼츠 후보 자동 생성 파이프라인 — 프로젝트 점검 기준 문서

> 장편 드라마 에피소드를 분석해 9:16 세로형 쇼츠 후보 클립을 자동 생성하는 시스템의 전체 설계·현재 상태·병목·우선순위를 기록한다.
> 실제 코드베이스(`backend/app/services/`, `backend/app/tasks/`) 기반으로 작성하며, 구현 상태와 향후 계획을 항상 분리한다.

---

## 다음 우선순위 — LLM-first 후보 생성 파이프라인 전환

### 배경: 현재 heuristic 파이프라인의 근본 한계

현재 후보 생성은 17개 통계 프록시(speech_coverage, qa_score, tone_signals 등)를 가중 합산하는 heuristic 방식이다. 이 방식은 “대사가 많으면 좋겠지”, “질문-답변 구조면 좋겠지” 같은 표면적 신호만 잡을 수 있고, **”이 장면이 왜 재밌는지”, “맥락 없이도 이해되는지”** 같은 의미 이해는 불가능하다.

**결론: 후보 선정의 주력을 heuristic에서 LLM으로 전환한다.**

### 목표 구조: LLM-first + Heuristic-fallback

```
[에피소드 자막 전체]
       │
       ▼
┌─────────────────────────────────────┐
│  Phase 2A: LLM 후보 추천 (주력)     │
│                                     │
│  에피소드 전체 자막 → LLM 1회 호출  │
│  “쇼츠로 뽑을 만한 구간 10개를     │
│   시간 범위 + 이유 + 제목과 함께    │
│   골라줘”                          │
│  → LLM 추천 구간 10개              │
└─────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────┐
│  Phase 2B: 보정 + 병합              │
│                                     │
│  - 샷 경계에 맞춰 트림 보정         │
│  - LengthPolicy 적용               │
│  - 기존 heuristic fallback 병합     │
│    (LLM 실패 시 / API 키 없을 시)  │
│  - 시각/오디오 시그널 보정 점수      │
│  - diversity-aware dedupe           │
│  → 최대 14개 Candidate             │
└─────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────┐
│  기존 Phase 4-5 유지                │
│  Vision rerank / 렌더 / 피드백      │
└─────────────────────────────────────┘
```

### 설계 원칙

1. **LLM이 “어디를” 결정, 기존 파이프라인이 “어떻게” 처리** — 샷 감지, 길이 정책, dedupe, 렌더링, 피드백 루프는 그대로 유지
2. **Graceful fallback** — `OPENAI_API_KEY` 없거나 LLM 호출 실패 시 기존 heuristic 경로로 자동 전환 (현재와 동일하게 동작)
3. **비용 합리성** — 에피소드 자막 3000~8000 토큰, gpt-5.1-mini 1회 호출 ~$0.01–0.05
4. **기존 자산 보존** — Phase 1(분석), Phase 4-5(정제/렌더/피드백)는 변경 없음

### 구현 단계

| 단계 | 내용 | 파일 | 상태 |
|------|------|------|------|
| **1** | **LLM 후보 추천 서비스 구현** — 시스템 프롬프트, 자막→LLM→구간 JSON 파싱, mock fallback, ScoredWindow 변환 | `services/llm_candidate_service.py` | ✅ 완료 |
| **2** | **config/환경변수 추가** — `LLM_CANDIDATE_ENABLED`, `LLM_CANDIDATE_MODEL`, `LLM_CANDIDATE_MAX_SUGGESTIONS` | `core/config.py` | ✅ 완료 |
| **3** | **generate_candidates_step에 LLM-first 경로 통합** — LLM 추천 → heuristic 병합 → dedupe | `services/analysis_service.py` | ✅ 완료 |
| **4** | **테스트 12건 추가** — 자막 포맷, JSON 파싱, score clamp, fallback, ScoredWindow 변환 | `tests/test_llm_candidate_service.py` | ✅ 완료 |
| **5** | **plan.md 갱신** | `plan.md` | ✅ 완료 |

### 핵심 결정 사항

| 결정 | 선택 | 이유 |
|------|------|------|
| LLM 모델 | `gpt-5.1-mini` (기본) | 비용 대비 품질 최적. 필요 시 `gpt-5.1`로 승격 가능 |
| 입력 | 자막 텍스트 전체 (타임스탬프 포함) | 영상 바이너리 불필요. 토큰 효율적 |
| 출력 형식 | JSON — `[{start_time, end_time, title, reason, score}]` | 파싱 용이, 기존 ScoredWindow 구조와 매핑 |
| fallback | `ALLOW_MOCK_LLM_FALLBACK=true` 시 기존 heuristic 전체 사용 | 현재 동작과 동일 |
| 기존 heuristic | LLM 실패/비활성 시 fallback으로 유지 | 점진적 전환, 비교 실험 가능 |

### 후속 개선 (LLM-first 품질 보강)

| 우선순위 | 항목 | 설명 | 영향 |
|----------|------|------|------|
| ~~**1**~~ ✅ | ~~**LLM 추천 구간을 샷 경계에 스냅**~~ | `_snap_to_shot_boundaries()` — 각 끝점에서 5초 이내 가장 가까운 샷 경계로 스냅. 메타데이터에 `shot_snapped`, `original_start/end` 기록. | 렌더링 품질 직접 향상 |
| ~~**2**~~ ✅ | ~~**LLM 후보에 시각/오디오 보정 점수 부여**~~ | `compute_visual_impact()` 재사용, `speech_coverage`/`cuts_inside` 계산. `scores_json`에 `visual_impact`, `visual_bonus`, `speech_coverage` 추가. | dedupe 품질 + 메타데이터 풍부화 |
| ~~**3**~~ ✅ | ~~**LLM/heuristic 점수 스케일 정규화**~~ | `_LLM_SCORE_SCALE=0.85` 계수 적용. LLM 8.0 → 6.8로 정규화 + visual_bonus 가산. `llm_score_normalized` 필드로 추적. | 두 경로 간 공정 경쟁 |
| ~~**4**~~ ✅ | ~~**LLM 응답 캐싱**~~ | `stable_hash(자막+프롬프트버전+장르+모델)` 기반 JSON 캐시. `LLM_CANDIDATE_CACHE_ENABLED=true`. `storage/cache/llm_candidates/` 저장. | 비용 절감 |
| ~~**5**~~ ✅ | ~~**프롬프트 A/B 테스트**~~ | `LLM_CANDIDATE_PROMPT_VERSION=v1|v2`. v1=편집 전문가, v2=큐레이터 톤. `_PROMPT_VERSIONS` dict로 관리. 캐시 키에 버전 포함. | 프롬프트 품질 실증 |
| ~~**6**~~ ✅ | ~~**장르별 프롬프트 분기**~~ | `episode.target_channel` → `_GENRE_CRITERIA` 자동 주입. 드라마(갈등/반전), 예능(리액션/유머), 다큐(충격/감동). 미등록 장르는 기본 기준만. | 장르 최적화 |

### 다음 개선 (후보 퀄리티 심화)

| 우선순위 | 항목 | 설명 | 영향 | 추가 비용 |
|----------|------|------|------|----------|
| ~~**7**~~ ✅ | ~~**LLM 2-pass: 추천 → 검증**~~ | `verify_candidates_with_llm()` — Pass 2에서 각 후보 keep/drop + 트림 조정 + 점수 재산정. `LLM_CANDIDATE_VERIFY_ENABLED=true`로 활성화. 실패 시 원본 유지. | 부적격 탈락 + 트림 정밀도 | 에피소드당 ~$0.05 |
| ~~**8**~~ ✅ | ~~**채택 이력 few-shot 주입**~~ | `_build_few_shot_examples(db)` — DB selected=True 후보 최근 N개를 프롬프트에 삽입. `LLM_CANDIDATE_FEW_SHOT_COUNT=5`. 채택 이력 없으면 기존 프롬프트 그대로. | 운영 기준 반영, 즉시 품질 향상 | 프롬프트 토큰 소폭 증가 |
| ~~**9**~~ ✅ | ~~**끝점을 자막 문장 경계에 스냅**~~ | `_snap_end_to_sentence_boundary()` — 끝점에서 8초 이내 마지막 완결 자막의 end_time으로 당김. 구간이 25초 미만이 되면 원본 유지. metadata에 `sentence_snapped` 기록. | 끝점 자연스러움 직접 향상 | 없음 |
| ~~**10**~~ ✅ | ~~**중간 이질 씬 감지 → 자동 composite 분리**~~ | `_detect_foreign_scene_gaps()` — 구간 내 자막 공백이 8초 이상이면 clip_spans 분리. `arc_form=composite`, `composite=true` 설정. 기존 composite 렌더 인프라 재사용. 5초 미만 span 자동 제거. | 중간 끊김 없는 깔끔한 클립 | 없음 |
| ~~**11**~~ ✅ | ~~**자막 인라인 편집 → 원본 DB 동시 업데이트**~~ | 쇼츠 편집 화면의 자막 textarea에서 수정 후 포커스 벗어나면 `PATCH /transcript-segments/{id}` 호출로 원본 `TranscriptSegment.text` 즉시 반영. 렌더링용 override와 원본 DB 동시 갱신. 재분석 시 수정된 자막 기준. | 자막 수정→재분석 워크플로우 완성 | 없음 |

#### 7: LLM 2-pass 설계

```
Pass 1 (기존)                    Pass 2 (신규)
─────────────────               ─────────────────
자막 전체 → LLM                 후보별 자막 발췌 → LLM
"후보 10개 골라줘"              "이 구간을 검증해줘"
→ 구간 10개                     → 각 후보에 대해:
                                  - keep / drop 판정
                                  - 트림 조정 제안 (±N초)
                                  - 최종 score 재산정
                                  - 이유 보강
→ 검증 통과 후보만 ScoredWindow로 변환
```

**구현 방식:**
- `llm_candidate_service.py`에 `verify_candidates_with_llm()` 함수 추가
- Pass 1 결과 + 해당 구간 자막 발췌를 LLM에 전달
- 응답: `{keep: bool, adjusted_start, adjusted_end, final_score, reason}`
- `keep=false`이면 탈락, `adjusted_start/end`가 다르면 트림 보정
- analysis_service.py에서 Pass 1 → Pass 2 → 샷 스냅 → heuristic 병합 순서

**환경변수:**
- `LLM_CANDIDATE_VERIFY_ENABLED=true` — Pass 2 활성화 (기본 비활성)
- `LLM_CANDIDATE_VERIFY_MODEL=gpt-5.1-mini` — 검증용 모델 (Pass 1과 같거나 다를 수 있음)

#### 8: 채택 이력 few-shot 주입 설계

```
기존 프롬프트                     개선 프롬프트
─────────────                    ─────────────
시스템: "좋은 쇼츠란..."         시스템: "좋은 쇼츠란..."
                                 + "이전에 채택된 쇼츠 예시:"
                                 +   예시 1: [120.5–175.0] "제목" — 발췌...
                                 +   예시 2: [340.0–400.0] "제목" — 발췌...
                                 +   예시 3: ...
유저: "자막에서 골라줘"          유저: "자막에서 골라줘"
```

**구현 방식:**
- `llm_candidate_service.py`에 `_build_few_shot_examples()` 함수 추가
- DB에서 같은 show_title (또는 전체)의 `selected=True` 후보를 최근 N개 조회
- 각 후보의 `transcript_excerpt`(≤200자) + `title_hint`를 프롬프트에 삽입
- few-shot 예시가 없으면 (운영 초기) 기존 프롬프트 그대로 동작
- analysis_service.py에서 `db` 세션을 `suggest_candidates_with_llm()`에 전달

**환경변수:**
- `LLM_CANDIDATE_FEW_SHOT_COUNT=5` — few-shot 예시 최대 수

---

## 완료된 피드백 루프 구현 요약

아래 항목은 모두 구현 완료 ✅

| 영역 | 구현 내용 |
|------|----------|
| **feedback → 상태 변경** | `_apply_feedback_action()`으로 selected/rejected/edited/reordered 액션이 Candidate 상태를 실제 변경 |
| **reordered 전체 재정렬** | `_reorder_episode_candidates()`로 episode 내 전체 후보 index shift, 동적 clamp, metadata에 reorder_from/to/count 기록 |
| **failure_tags 동기화** | 피드백 생성 시 항상 overwrite+dedupe (`default_factory=list`, `[]`=clear) |
| **CandidateDetailResponse 확장** | `selected`, `failure_tags`, `feedback_summary`(count/action/at/reason) 직접 노출 |
| **created_seq deterministic 정렬** | `CandidateFeedback.created_seq` auto-increment 컬럼, `created_seq DESC NULLS LAST, created_at DESC` 기준 |
| **회귀 테스트 26건** | selected/rejected 상태전이, failure_tags clear/sync, reorder 전체순위/clamp/metadata, snapshot 완전성, validation, detail summary, evaluate 집계 |
| **프론트 피드백 패널** | new_rank 입력 UI, 한글 액션/태그 라벨, 성공 메시지 “4위→2위 이동 완료”, 상태 실시간 반영 |
| **evaluate 리포트 확장** | `--include-db-feedback` 옵션, failure_tag별 평균점수, track×failure 교차표, window_reason×status 분포 |

---


## 목차

1. [문서 목적 / 범위 / 업데이트 원칙](#1-문서-목적--범위--업데이트-원칙)
2. [제품 목표와 성공 기준](#2-제품-목표와-성공-기준)
3. [현재 파이프라인 한눈에 보기](#3-현재-파이프라인-한눈에-보기)
4. [현재 구현 상태](#4-현재-구현-상태)
5. [후보 선정 품질 가설](#5-후보-선정-품질-가설)
6. [현재 병목과 실패 유형](#6-현재-병목과-실패-유형)
7. [우선순위 로드맵](#7-우선순위-로드맵)
8. [파이프라인 상세](#8-파이프라인-상세)
9. [평가 / 테스트 / 피드백 루프](#9-평가--테스트--피드백-루프)
10. [운영 레퍼런스](#10-운영-레퍼런스)
- [부록 A. 핵심 데이터 구조](#부록-a-핵심-데이터-구조)
- [부록 B. 환경 설정 빠른 참조](#부록-b-환경-설정-빠른-참조)
- [부록 C. Canonical Schema & Vocabulary](#부록-c-canonical-schema--vocabulary-고정-인터페이스)
- [부록 D. 기술 분석 상세](#부록-d-기술-분석-상세)

---

## 1. 문서 목적 / 범위 / 업데이트 원칙

이 문서는 **레포를 처음 보는 사람도 현재 상태·핵심 설계·병목·우선순위를 한 번에 파악**할 수 있는 "프로젝트 전체 점검 기준 문서"다. 구현 진행 중인 기능과 향후 계획이 뒤섞이지 않도록 상태 분류를 명시한다.

**구현 상태 분류 체계:**

| 상태 | 의미 |
|------|------|
| **production-ready** | 실전 기본 경로로 항상 동작 |
| **integrated, off by default** | 코드·feature flag 연결됨, 기본 비활성 (설정 켜야 동작) |
| **implemented, local/eval only** | 구현됐지만 실전 파이프라인 기본 경로 아님 |
| **experimental** | 선택적, 비용/의존성 이유로 기본 비활성 |
| **out of scope** | MVP 범위 밖, 필요성 검증 후 도입 결정 |

**원칙:**
- 현재 상태와 향후 계획을 절대 섞지 않는다. 향후 계획은 반드시 "향후", "예정", "미구현" 표현을 사용한다.
- 코드 변경 시 §4 구현 상태 표를 먼저 업데이트하고 관련 서비스를 일괄 수정한다.
- 부록 C의 Canonical Schema 변경 시 관련 서비스를 일괄 수정한다.

---

## 2. 제품 목표와 성공 기준

**무엇을 만드는가:** 장편 드라마 에피소드(MP4 + 선택적 SRT)를 로컬 머신에서 분석해, 편집자가 골라서 쓸 수 있는 9:16 세로형 쇼츠 후보 클립 세트를 자동으로 생성한다. AWS 등 외부 클라우드 의존성 없이 단일 머신에서 동작한다.

**성공 기준:** 운영자가 후보 세트(최대 14개)를 보고 "편집할 만한 클립"을 빠르게 고를 수 있는 수준. 운영자가 처음부터 직접 타임라인을 탐색하는 시간을 대폭 단축한다.

**정량 지표:**

| 지표 | 설명 | 현황 |
|------|------|------|
| Recall@K | 운영자가 채택한 후보가 상위 K개 안에 있는 비율 | `evaluate_candidates.py` 구현됨, golden set 축적 필요 |
| 채택율 | 생성된 후보 중 운영자가 실제 선택한 비율 | 피드백 루프 구현 완료, `--include-db-feedback`으로 집계 가능 |
| 후보 다양성 | 상위 K개 후보의 인물·사건·payoff 유형 분산 | diversity-aware selection 구현됨, track×failure 교차표 |

---

## 3. 현재 파이프라인 한눈에 보기

### 데이터 흐름도

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
│  extract_or_generate_transcript     │
│    → SRT 파싱 / Whisper ASR / none │
│  compute_signals                    │
│    → speech ratio, cut density 등   │
└─────────────────────────────────────┘
          │
          ▼ (Shot[], TranscriptSegment[])
┌─────────────────────────────────────┐
│  Phase 2A: LLM 후보 추천 (주력)     │
│  [LLM_CANDIDATE_ENABLED=true 시]   │
│                                     │
│  suggest_candidates_with_llm()     │
│    → 에피소드 전체 자막 → LLM      │
│    → 구간 추천 JSON 파싱            │
│    → ScoredWindow[] (llm track)    │
│    → 실패 시 빈 리스트 (fallback)  │
└─────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────┐
│  Phase 2B: Heuristic (보완/fallback)│
│                                     │
│  build_candidates_for_episode()     │
│    → 3-Track Seed + score_window() │
│    → composite candidates           │
│                                     │
│  LLM 후보 + Heuristic 후보 병합    │
│    → rerank + dedupe                │
│    → 최대 14개 Candidate           │
└─────────────────────────────────────┘
          │
          ▼ (ScoredWindow[14])
┌─────────────────────────────────────┐
│  Phase 4: Vision·LLM 정제           │
│  [experimental — 기본 비활성]       │
│                                     │
│  refine_candidates_with_vision()    │
│    → 상위 8개 × GPT-4V 재랭크       │
│    → score_delta [-1.5, +1.5]       │
│                                     │
│  llm_arc_judge() [기본 비활성]      │
│    → gpt-5.1-mini 서사 판정        │
└─────────────────────────────────────┘
          │
          ▼ (Candidate DB 저장)
┌─────────────────────────────────────┐
│  Phase 5: 사용자 워크플로우         │
│                                     │
│  ScriptDraft 생성 (OpenAI/Mock)     │
│  VideoDraft 렌더링 (FFmpeg)         │
│  ShortClip 렌더링 (FFmpeg)          │
│  Export 패키징                      │
└─────────────────────────────────────┘
```

### 길이 정책 분리

"길게 탐색하되 짧고 강한 결과를 뽑는 구조"로 설계되어 있다. search window는 넓게 잡아 후보를 놓치지 않고, 실제 출력 쇼츠는 코어 아크 합산 기준으로 짧게 유지한다.

| 개념 | 범위 | 실제 값 |
|------|------|---------|
| 탐색 윈도우 (search window) | micro-event 기반 후보 탐색 범위 | 30 – 180초 |
| 코어 아크 합산 (core span total) | 복합 후보의 코어 스팬 합산 | 2-span ≤ 64초, 3-span ≤ 90초 |
| 최종 렌더 타깃 (render target) | 실제 출력 쇼츠 목표 길이 | 30 – 75초 권장 (코어 기준) |

---

## 4. 현재 구현 상태

| 구성요소 | 파일 | 상태 | 비고 |
|----------|------|------|------|
| FFmpeg 프록시 트랜스코딩 | `proxy_transcoding.py` | **production-ready** | 480p/6fps, CRF 31, 캐싱 |
| Scene 감지 (샷 경계) | `shot_detection.py` | **production-ready** | FFmpeg scene filter, 임계값 0.32 |
| Keyframe 추출 | `keyframe_extraction.py` | **production-ready** | 샷당 6프레임 균등 추출 |
| SRT/WebVTT 자막 파싱 | `subtitle_parse.py` | **production-ready** | SRT/WebVTT 업로드 파일 지원 |
| 자막 인라인 편집 | `episodes.py`, `short-clip-panel.tsx` | **production-ready** | `PATCH /transcript-segments/{id}` — 쇼츠 편집 화면에서 원본 DB 자막 즉시 수정 |
| Micro-event 생성 | `candidate_events.py` | **production-ready** | 자막 큐 → CandidateEvent 병합 |
| 서사 역할 점수 | `candidate_role_scoring.py` | **production-ready** | setup/escalation/payoff/reaction/standalone 점수 |
| 구조 시그널 (QA/payoff/reaction) | `candidate_structure_signals.py` | **production-ready** | 6개 구조 시그널 함수 |
| 시각 시그널 (Track B) | `candidate_visual_signals.py` | **production-ready** | 컷 밀도 스파이크·반응샷 패턴 |
| 오디오 에너지 프로파일 v2 | `candidate_audio_signals.py` | **production-ready** | Track C `generate_audio_seeds_live()`, ebur128 기본 경로 |
| 윈도우 스코어링 (3-Track) | `candidate_generation.py` | **production-ready** | ScoringWeights 프로파일 포함 |
| 빔 서치 Arc 탐색 | `candidate_arc_search.py` | **production-ready** | BEAM_WIDTH=16, MAX_ARC_DEPTH=4 |
| 복합 후보 생성 (2-span + 3-span) | `composite_candidate_generation.py` | **production-ready** | 2-span ≤ 64초, 3-span ≤ 90초 |
| Arc 기반 재랭크 | `candidate_rerank.py` | **production-ready** | arc_quality_delta [-1.5, +1.5] |
| 쇼츠 클립 FFmpeg 렌더 | `short_clip_service.py` | **production-ready** | 9:16, cover/pad-blur/contain 모드 |
| ASS 자막 burn-in | `subtitle_exchange.py` | **production-ready** | NanumGothic 72pt, 1080×1920 |
| 스크립트 생성 (OpenAI) | `script_service.py` | **production-ready** | Mock fallback 포함 |
| Celery 파이프라인 체인 | `tasks/pipelines.py` | **production-ready** | 7단계 chain, 10%→100% |
| 성능 계측 (perf dict) | `analysis_service.py` | **production-ready** | `candidate_gen_perf` in metadata_json |
| Entity 강화 (NER + 화자) | `entity_service.py` | **production-ready** | 한국어 NER + 화자 레이블 패턴 파싱 |
| TTS 렌더링 | `tts_service.py` | **production-ready** | OpenAI gpt-4o-mini-tts + silence 폴백 |
| 비디오 템플릿 렌더러 | `video_template_renderer.py` | **production-ready** | FFmpeg ASS 자막·텍스트 슬롯·TTS |
| Whisper ASR | `asr_service.py` | **integrated, off by default** | `ASR_ENABLED=True` 필요; faster-whisper/openai-whisper 폴백 |
| ML 임베딩 언어 시그널 | `candidate_language_signals.py` | **integrated, off by default** | `EMBEDDING_SIGNALS_ENABLED=true` + API 키 필요; 기본 keyword 폴백 |
| librosa 고급 오디오 분석 | `audio_analysis_service.py` | **integrated, off by default** | `AUDIO_ANALYSIS_BACKEND=librosa/auto` 시 활성; Track C optional 보정 |
| 오프라인 평가 스크립트 v2 | `scripts/evaluate_candidates.py` | **implemented, local/eval only** | golden set v2 (quality/failure_types), Recall@K 매칭 상세, DB export/seed, 실패 유형 분포 |
| 실패 유형 분류 체계 | `models.py`, `candidate_feedback.py` | **production-ready** | `FailureType` enum 7종, `Candidate.failure_tags` 컬럼, PUT/GET API |
| 후보 다양성 강화 (diversity-aware) | `candidate_generation.py` | **production-ready** | entity Jaccard + window_reason + ranking_focus 기반 diversity penalty, greedy selection |
| 길이 정책 3계층 분리 | `candidate_generation.py`, `config.py` | **production-ready** | `LengthPolicy` dataclass, 환경변수 연동 (search window / core span / render target) |
| 운영자 피드백 로그 | `models.py`, `candidate_feedback.py` | **production-ready** | `CandidateFeedback` 모델, 마이그레이션 0005/0006, POST/GET API, 프론트엔드 패널 |
| 피드백 → Candidate 상태 변경 | `candidate_feedback.py` | **production-ready** | selected/rejected/edited/reordered 상태변경, snapshot, failure_tags 동기화, `FeedbackMetadata` 타입, created_seq retry-on-conflict |
| 피드백 순서 보장 (created_seq) | `models.py`, `candidate_read.py` | **production-ready** | `created_seq` auto-increment 컬럼, deterministic latest 선택, 마이그레이션 0006 |
| 피드백 회귀 테스트 | `tests/test_candidate_feedback.py` | **production-ready** | 26건 pytest: 상태전이, failure_tags, reorder, snapshot, validation, summary, evaluate |
| Vision 재랭크 v2 (GPT-4.1) | `vision_candidate_refinement.py` | **experimental** | `VISION_CANDIDATE_RERANK=true` + API 키; 비용 발생 |
| LLM Arc Judge | `candidate_rerank.py` | **experimental** | `LLM_ARC_JUDGE_ENABLED=true`; gpt-5.1-mini, 비용 발생 |
| **LLM-first 후보 추천** | `llm_candidate_service.py` | **integrated, off by default** | `LLM_CANDIDATE_ENABLED=true` + API 키. 2-pass(추천→검증), few-shot 주입, 샷 스냅, 시각 보정, 점수 정규화, 응답 캐싱, 프롬프트 A/B, 장르별 분기. 34건 테스트. |
| Speaker Diarization | — | **out of scope** | pyannote.audio 의존성 큼; 향후 필요성 검증 후 도입 결정 |
| YouTube 자동 업로드 | — | **out of scope** | 채널 할당량(~6건/일) 확인 후 도입 결정 |

---

## 5. 후보 선정 품질 가설

### 5.1 LLM-first 접근 (다음 구현 — 주력 경로)

현재 heuristic 3-Track 방식의 근본 한계: 17개 통계 프록시로는 **"이 장면이 왜 재밌는지"를 판단할 수 없다**. 대사 밀도가 높다고 좋은 쇼츠가 아니고, QA 구조가 있다고 독립 시청이 가능한 것도 아니다.

**해결: 에피소드 전체 자막을 LLM에 넣고, "쇼츠로 뽑을 만한 구간"을 직접 추천받는다.**
- LLM이 서사 구조, 감정 흐름, 독립 이해 가능성을 **의미 수준에서** 판단
- 비용: gpt-5.1-mini 기준 에피소드당 ~$0.01–0.05 (자막 3000~8000 토큰)
- 기존 heuristic은 LLM 실패/비활성 시 fallback으로 유지

### 5.2 기존 3-Track Heuristic (fallback 경로)

- **Track A (대화):** 대화 밀도·QA 구조 기반. LLM 없을 때 가장 신뢰도 높은 시그널.
- **Track B (시각):** 컷 전환·반응샷. 자막 없는 구간에서 독립 탐색.
- **Track C (오디오):** 음량 에너지 스파이크. 클라이맥스/전환점 포착.
- LLM-first 전환 후에도 샷 경계 보정, 시각/오디오 보정 점수, dedupe에는 계속 활용.

### 5.3 Arc/Composite 가설

- 쇼츠는 "setup → payoff" 아크가 명확할수록 독립 시청 가능하다.
- **contiguous:** 연속 대화에서 자연스러운 아크. 이벤트 간 간격이 모두 12초 이하인 경우.
- **composite:** 시간적으로 떨어진 이벤트를 연결해 더 강한 아크 구성 가능. 2-span(setup+payoff)과 3-span(setup+escalation+payoff)을 지원한다.
- LLM-first 전환 후에도 LLM 추천 구간이 composite 형태일 수 있으므로 기존 composite 렌더링은 유지.

### 5.4 왜 LLM-first가 낫나

| 관점 | Heuristic (현재) | LLM-first (전환 목표) |
|------|-----------------|---------------------|
| **의미 이해** | 없음 — 키워드·통계 프록시 | 있음 — 서사 구조, 감정, 독립성 판단 |
| **첫 에피소드 품질** | 가중치 주관적 초기값 | 즉시 의미 기반 추천 |
| **비용** | 무료 | 에피소드당 ~$0.01–0.05 |
| **fallback** | — | heuristic 전체를 fallback으로 유지 |
| **튜닝** | golden set + 가중치 조정 필요 | 프롬프트 개선으로 즉시 반영 |

---

## 6. 현재 병목과 실패 유형

### 6.1 알려진 실패 유형

| 실패 유형 | 발생 원인 | 현재 완화 장치 | 미해결 여부 |
|-----------|-----------|----------------|-------------|
| 맥락 없이는 이해 불가한 후보 | 아크 탐색이 넓은 window 허용 | `standalone_clarity_score`, `context_dependency_score` | 부분 완화 |
| payoff 없이 끊기는 후보 | arc 탐색 실패, 짧은 에피소드 | `payoff_end_weight`, beam search arc | 부분 완화 |
| 유사한 후보 여러 개 상위 노출 | IOU NMS + Jaccard dedupe만 적용 | IOU 0.52 + Jaccard + diversity-aware selection (entity/reason/focus 패널티) | ✅ 해결: diversity-aware greedy selection 구현 |
| 지나치게 긴 후보 | 180초까지 search window 허용 | MAX_WINDOW_SEC=180, render target 별도 | 부분 완화 |
| 시각적으로는 강하지만 내러티브 약한 후보 | Track B 시각 시그널 과중 | ScoringWeights 프로파일로 조정 가능 | 운영자 피드백 없이는 조정 근거 부족 |
| 대사만 세고 쇼츠 구조 약한 후보 | hookability_score가 단일 지표 | `hookability_score` (첫 이벤트 강도) | **미해결**: 구조 품질 평가 지표 부족 |
| 복합 후보 과연결 | composite 조합 3-span까지 허용 | 90초 길이 제한, coherence ≥ 0.10 | **미해결**: 편집 복잡도 평가 없음 |

### 6.2 현재 평가 체계

- **오프라인 평가셋 v2:** golden set v2 스키마(quality: good/acceptable/bad, failure_types, notes) 지원. DB 후보를 seed로 템플릿 생성 가능. 실 드라마 에피소드 기반 golden set 축적 필요.
- **Recall@K 계산 스크립트** (`evaluate_candidates.py`): golden별 매칭 상세(best_iou, best_candidate_rank), 실패 유형 분포, 트랙별 분포, 품질 분포 집계 지원.
- **운영자 피드백 루프:** `CandidateFeedback` DB 모델 + API + 프론트엔드 피드백 패널. 피드백 액션이 Candidate 상태를 실제 변경하고, `failure_tags`도 동기화. `created_seq` 기반 deterministic 정렬. `evaluate_candidates.py --include-db-feedback`으로 운영 피드백 집계.

### 6.3 현재 핵심 병목

1. ~~**golden set 부재**~~ → ✅ golden set v2 스키마 + evaluate_candidates.py v2 구현 완료. 실 에피소드 데이터 축적 필요.
2. **scoring weight 근거 부족** → 현재 default 가중치가 최적인지 알 수 없음. golden set 축적 후 실증 실험 필요.
3. ~~**다양성 보장 없음**~~ → ✅ diversity-aware selection 구현 (entity/reason/focus 중복 패널티)

---

## 7. 우선순위 로드맵

### 즉시 — LLM-first 후보 생성 전환

| 항목 | 상태 | 설명 |
|------|------|------|
| ~~LLM 후보 추천 서비스~~ | ✅ 완료 | `llm_candidate_service.py` — 자막 전체 → LLM → 구간 추천 JSON, mock fallback |
| ~~generate_candidates에 LLM-first 통합~~ | ✅ 완료 | LLM 추천 → heuristic fallback 병합 → dedupe |
| ~~config/환경변수~~ | ✅ 완료 | `LLM_CANDIDATE_ENABLED`, `LLM_CANDIDATE_MODEL`, `LLM_CANDIDATE_MAX_SUGGESTIONS` |
| ~~테스트 12건~~ | ✅ 완료 | 자막 포맷, JSON 파싱, score clamp, fallback, ScoredWindow 변환 |

### 완료된 항목

| 항목 | 상태 | 구현 내용 |
|------|------|----------|
| ~~오프라인 평가셋 정교화~~ | ✅ 완료 | golden set v2 스키마, Recall@K 매칭 상세, DB export/seed, 실패 유형 분포 |
| ~~실패 유형 taxonomy~~ | ✅ 완료 | `FailureType` enum 7종, `failure_tags` DB 컬럼, PUT/GET API, 프론트엔드 태깅 UI |
| ~~diversity-aware selection~~ | ✅ 완료 | `_diversity_penalty()` entity/reason/focus 중복 패널티 + greedy selection |
| ~~운영자 피드백 루프~~ | ✅ 완료 | 상태변경, failure_tags 동기화, created_seq, 26건 테스트, 프론트 패널 |
| ~~길이 정책 3계층~~ | ✅ 완료 | `LengthPolicy` dataclass, 환경변수 연동 |

### 향후 (LLM-first 안정화 이후)

- **ScoringWeights 튜닝:** golden set 축적 후 heuristic fallback 가중치 실증 조정
- **프롬프트 A/B 테스트:** LLM 프롬프트 버전별 채택율 비교
- **장르별 프롬프트 분기:** 드라마/예능/다큐 등 장르 인식 후 프롬프트 전환
- **pairwise ranking:** 피드백 로그 기반 선호 쌍 → reranker 학습
- **Speaker Diarization:** pyannote.audio 의존성 평가 후 도입 결정

---

## 8. 파이프라인 상세

### 8.1 Phase 1 — 분석 파이프라인

#### FFmpeg 프록시 트랜스코딩 (`proxy_transcoding.py`)

**목적:** 원본 고화질 영상(수 GB) 대신 분석용 소형 프록시로 처리 속도 극대화.

프록시 영상: 480p 축소, 6 FPS, CRF 31, `-preset veryfast`, 오디오 제거. 오디오는 64k AAC로 별도 추출.

**캐싱 전략:** `cache_utils.file_signature(path)`(크기 + mtime 해시)를 기반으로 동일 파일 재처리 방지.

#### 샷 감지 (`shot_detection.py`)

FFmpeg `select='gt(scene,0.32)'` 필터 활용. 0.28초 미만 간격 연속 샷 병합, 최대 100샷 상한. 감지 실패 시 균등 분할 폴백.

#### Keyframe 추출 (`keyframe_extraction.py`)

샷당 6프레임 균등 간격 추출. Vision 재랭크 시 후보 윈도우 내 프레임에서 균등 6개 선택.

저장 경로: `storage/episodes/{id}/shots/{shot_index:04d}/frame_{n:03d}.jpg`

#### 자막 파싱 및 ASR (`subtitle_parse.py`, `asr_service.py`)

`extract_or_generate_transcript_step()`은 세 가지 브랜치:
1. **업로드된 자막 우선:** `episode.source_subtitle_path` 있으면 SRT/WebVTT 파싱
2. **Whisper ASR (설정 시):** `ASR_ENABLED=True`이면 faster-whisper → openai-whisper 순 폴백 — **integrated, off by default**
3. **없음:** 빈 segment 목록 (파이프라인 계속 진행)

---

### 8.2 Phase 2 — 후보 생성 엔진

#### Micro-Event 생성 (`candidate_events.py`)

자막 큐를 의미 단위인 `CandidateEvent`로 병합. 경계 조건: 현재 큐 지속시간 ≥ 18초, 간격 ≥ 1.8초, 문장 종결 부호, reaction/payoff/question 신호 임계값 달성 시 경계 확정.

#### 3-Track 윈도우 생성

**Track A (대화 구조, `_enumerate_windows`):**
- events 슬라이스(최대 10개)로 30–180초 윈도우 열거
- window_reason 우선순위: `question_answer` > `reaction_shift` > `payoff_end` > `hook_open` > `tail_*` > `compact_dialogue_turn`
- reason 없는 윈도우는 폐기. 이벤트 없으면 샷 경계 폴백

**Track B (시각 임팩트, `candidate_visual_signals.py`):**
- 컷 밀도 스파이크: 로컬 컷 빈도 > 에피소드 평균 × 1.5인 구간
- 반응샷 패턴: 3개 이상 연속 2초 미만 샷
- 저대사 고시각: speech_coverage < 0.3 AND cut_density > 평균

**Track C (오디오 반응, `candidate_audio_signals.py`):**
- `generate_audio_seeds_live()` 단일 진입점
- ebur128 기본 경로 → astats 자동 폴백 → librosa optional 보정 (`AUDIO_ANALYSIS_BACKEND=librosa/auto` 시)
- 오디오 임팩트 ≥ 0.2인 구간을 앵커로 pre_pad + post_pad 조합, 최대 10개 시드

#### 윈도우 스코어링 (`score_window`, `candidate_generation.py`)

17개 컴포넌트 점수 가중 합산 → [1.0, 10.0] 정규화. 핵심 가중치:

| 컴포넌트 | 가중치 | 구현 파일 |
|----------|--------|-----------|
| `speech_coverage` | 12% | `candidate_generation.py` |
| `dialogue_density` | 10% | `candidate_structure_signals.py` |
| `qa_score` | 12% | `candidate_structure_signals.py` |
| `reaction_score` | 12% | `candidate_structure_signals.py` |
| `payoff_score` | 14% | `candidate_structure_signals.py` |
| `entity_score` | 6% | `candidate_structure_signals.py` |
| `clarity_score` | 10% | `candidate_structure_signals.py` |
| `hook_score` | 10% | `candidate_structure_signals.py` |
| `tone_signals` | 6% | `candidate_language_signals.py` |
| `cut_density` | 3% | `candidate_generation.py` |
| `visual_audio_bonus` | 5% | `candidate_generation.py` |
| `contiguous_bonus` | 가변 | arc_complete * 0.08 (arc ≥ 0.25만) |

**ScoringWeights 프로파일 (현재 구현된 3개):**

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

> 장르별 프로파일(drama_conflict, emotional_release, awkward_comedy 등)로 확장 가능한 축으로 설계됨 — 단, 현재 미구현. 향후 golden set 기반 실증 후 추가 예정.

#### 빔 서치 Arc 탐색 (`candidate_arc_search.py`)

setup_score 상위 20개 이벤트를 씨앗으로, BEAM_WIDTH=16, MAX_ARC_DEPTH=4, MAX_GAP_SEC=300초. gap > CONTIGUOUS_GAP_SEC(12초) 시 entity 겹침 필요 (overlap ≥ 0.05).

arc_form: 모든 인접 이벤트 간 간격 ≤ 12초이면 `contiguous`, 아니면 `composite`.

#### 복합 후보 생성 (`composite_candidate_generation.py`)

비연속 세그먼트를 묶는 복합 후보. 3단계 생성:
- **Phase 1:** `beam_search_arcs()` 결과 → ArcCandidate → ScoredWindow
- **Phase 2:** 최고 40개 윈도우의 쌍(pair) 휴리스틱 폴백 (gap 6–420초, total ≤ 64초)
- **Phase 3:** 상위 20개 윈도우의 3-스팬 트리플 (setup-escalation-payoff, total ≤ 90초, coherence ≥ 0.10)

#### 중복 제거 NMS (`dedupe_scored_windows`)

점수 내림차순 greedy 선택 후 두 가지 기준으로 중복 탈락:
1. 시간 IOU ≥ 0.52
2. 텍스트 Jaccard ≥ 0.82 AND (시간 겹침 ≥ 8초 OR 시작점 간격 ≤ 20초)

최대 14개 Candidate. diversity-aware greedy selection 적용: entity Jaccard, window_reason, ranking_focus 중복에 패널티를 부과해 다양성 보장.

---

### 8.3 Phase 4 — Vision·LLM 정제 (experimental)

두 컴포넌트 모두 **experimental** 상태로, 기본 비활성이다.

#### Vision 재랭크 (`vision_candidate_refinement.py`)

**호출 조건:** `VISION_CANDIDATE_RERANK=True` + `OPENAI_API_KEY` 존재. 상위 8개 후보에 GPT-4.1 Vision 적용.

파일 서명 기반 캐싱. 한국어 v2 시스템 프롬프트: score_delta(-1.5..1.5), visual_hook_score(0..10), self_contained_score(0..10), emotion_shift_score(0..10), thumbnail_strength_score(0..10), vision_reason, title_hint, note 반환.

#### LLM Arc Judge (`candidate_rerank.py`)

**호출 조건:** `LLM_ARC_JUDGE_ENABLED=True`. 상위 `LLM_ARC_JUDGE_TOP_K`(기본 5)개에 gpt-5.1-mini 적용. arc_closed(bool), standalone(0-10), shorts_fit(0-10), adjustment([-1.0, 1.0]), reason 반환.

---

### 8.4 Phase 5 — 렌더링 파이프라인

#### 쇼츠 클립 렌더링 (`short_clip_service.py`)

fit_mode: `cover` / `pad-blur` / `contain` (기본). ASS 자막 burn-in 선택적. 인코딩 품질 프리셋: veryfast(CRF 30)/fast(CRF 23)/medium(CRF 20).

출력 경로: `storage/episodes/{id}/candidates/{candidate_id}/short_clip_v{version}.mp4`

#### 내보내기 프리셋

| 프리셋 | 해상도 | CRF | 워터마크 |
|--------|--------|-----|---------|
| `shorts_default` | 1080×1920 | 23 | 없음 |
| `review_lowres` | 720×1280 | 30 | "INTERNAL REVIEW" |
| `archive_master` | 원본 유지 | 18 | 없음 |

---

## 9. 평가 / 테스트 / 피드백 루프

### 현재 구현된 평가 체계

**smoke test (`backend/scripts/smoke_test.py`):**
- 18초 합성 fixture (FFmpeg 흑색 + 440Hz 사인파) 기반
- 파이프라인 생존성 확인용. MIN_WINDOW_SEC=30이므로 실 후보 미생성이 정상
- Tests 18–22: 임베딩 disabled/no-key 폴백, audio_path=None 생존, 시드 메타데이터 검증 포함
- `make smoke` 또는 `python scripts/smoke_test.py`

**evaluate_candidates.py (`backend/scripts/evaluate_candidates.py`):** — **implemented, local/eval only**
- Recall@K (K=5/10/14), 점수 분포, 타임라인 커버리지, audio_track_candidate_count, embedding_used_candidate_count 집계
- golden set 없이는 Recall@K 측정 불가. 현재 의미 있는 측정 미실시.

### 현재 미구현 / 향후 도입 항목

- ~~**운영자 피드백 로그 스키마**~~ ✅ — `CandidateFeedback` DB 모델 + 마이그레이션 0005 + POST/GET API + 프론트엔드 피드백 패널로 구현 완료.
- ~~**golden set 기반 정량 평가**~~ ✅ — golden set v2 스키마(quality/failure_types) + evaluate_candidates.py v2 구현 완료. 실 에피소드 데이터 축적 필요.
- **pairwise ranking 데이터 생성 흐름:** 피드백 로그 → (후보 A vs 후보 B) 선호 쌍 → LLM-based reranker 또는 경량 ranking 모델 학습 준비. 현재 미구현.
- **피드백 회귀 테스트:** `backend/tests/test_candidate_feedback.py` — 26건 pytest (상태전이, failure_tags clear/sync, reorder 전체순위/clamp/metadata, snapshot, validation, detail summary, evaluate 집계, detail/list 일관성).
- **단위 테스트:** tone_signals·QA 스코어·Arc 탐색·IOU dedupe 4개 케이스. 현재 미구현.
- **통합 테스트:** 실 SRT + 영상 기반 E2E. 현재 미구현.

### 관측 / Observability

`candidate_gen_perf` dict in `episode.metadata_json`:

| 지표 | 측정 위치 | 경고 임계값 |
|------|-----------|-------------|
| `micro_event_count` | `build_micro_events()` 완료 후 | > 500개면 O(n²) 위험 |
| `beam_explored_states` | `beam_search_arcs()` 내 | > 50,000이면 시간 초과 위험 |
| `composite_gen_ms` | `build_composite_candidates()` 완료 후 | > 30,000ms |
| `candidate_gen_total_ms` | `generate_candidates_step()` 전체 | > 60,000ms |
| `vision_rerank_ms` | `refine_candidates_with_vision()` 완료 후 | > 120,000ms |
| `seeds_per_track` | 각 트랙 시드 생성 후 | Track A: 0이면 경고 |
| `embedding_signal_windows_used` | `score_window()` 내 | — |
| `audio_seed_backend` | Track C 완료 후 | — |

---

## 10. 운영 레퍼런스

### 실행 커맨드

```bash
# 백엔드 로컬 개발
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# smoke test
make smoke   # 또는: python scripts/smoke_test.py

# 린트/포맷
make lint    # Ruff
make format  # Ruff formatter

# 프론트엔드
cd frontend && npm install && npm run dev   # http://localhost:3000

# Docker 전체 스택
docker compose up --build   # Postgres + Redis + API + Worker
docker compose down -v      # 중지 + 볼륨 삭제
```

### 핵심 환경변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `DATABASE_URL` | `sqlite:///data/app.db` | PostgreSQL 또는 SQLite |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis URL |
| `CELERY_TASK_ALWAYS_EAGER` | `true` | true = 동기 실행 (smoke test용) |
| `OPENAI_API_KEY` | `""` | 없으면 Mock 폴백 |
| `ALLOW_MOCK_LLM_FALLBACK` | `true` | OpenAI 실패 시 결정적 Mock |
| `VISION_CANDIDATE_RERANK` | `true` | GPT-4.1 Vision 재랭크 (비용 발생) |
| `ASR_ENABLED` | `false` | Whisper ASR 활성화 |
| `WHISPER_MODEL_SIZE` | `medium` | tiny/base/small/medium/large |
| `AUDIO_ANALYSIS_BACKEND` | `ffmpeg` | ffmpeg/librosa/auto |
| `AUDIO_LIBROSA_ENABLED` | `false` | librosa 고급 분석 활성화 |
| `EMBEDDING_SIGNALS_ENABLED` | `false` | ML 임베딩 언어 시그널 (API 키 필요) |
| `LLM_ARC_JUDGE_ENABLED` | `false` | gpt-5.1-mini Arc Judge (비용 발생) |
| `LLM_ARC_JUDGE_TOP_K` | `5` | Arc Judge 적용 최대 후보 수 |
| `SCORING_PROFILE` | `default` | default/reaction_heavy/payoff_heavy |
| `LENGTH_MIN_WINDOW_SEC` | `30.0` | 탐색 윈도우 최소 (초) |
| `LENGTH_MAX_WINDOW_SEC` | `180.0` | 탐색 윈도우 최대 (초) |
| `LENGTH_MAX_2SPAN_SEC` | `64.0` | 2-span 코어 합산 상한 (초) |
| `LENGTH_MAX_3SPAN_SEC` | `90.0` | 3-span 코어 합산 상한 (초) |
| `LENGTH_RENDER_TARGET_MIN_SEC` | `30.0` | 렌더 타깃 최소 (초) |
| `LENGTH_RENDER_TARGET_MAX_SEC` | `75.0` | 렌더 타깃 최대 (초) |
| `LENGTH_RENDER_IDEAL_SEC` | `50.0` | 렌더 타깃 이상값 (초) |
| `STORAGE_ROOT` | `./storage` | 로컬 파일 저장 루트 |

### Celery 태스크 체인 구조

```python
# tasks/pipelines.py — launch_analysis_pipeline()
chain(
    ingest_episode.s(episode_id, job_id, ignore_cache),   # 10%
    transcode_proxy.s(job_id),                            # 30%
    detect_shots.s(job_id),                               # 45%
    extract_keyframes.s(job_id),                          # 52%
    extract_or_generate_transcript.s(job_id),             # 60%
    compute_signals.s(job_id),                            # 75%
    generate_candidates.s(job_id),                        # 90% → 100%
).apply_async()
```

각 태스크는 이전 태스크의 `payload: dict`를 입력으로 받아 `{**payload, "새_키": 결과}` 형식으로 전달. 실패 시 `_handle_step_failure()`가 Job 상태를 FAILED로 전환.

**별도 태스크 체인:**

| 체인 | 진입점 |
|------|--------|
| 스크립트 생성 | `generate_script_drafts_task` |
| 쇼츠 클립 렌더링 | `render_short_clip_task` |
| 비디오 초안 렌더링 | `render_video_draft_task` |
| 내보내기 렌더링 | `render_export_task` |

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
LLM_ARC_JUDGE_ENABLED=false       # gpt-5.1-mini Arc Judge (기본 비활성)
LLM_ARC_JUDGE_TOP_K=5
SCORING_PROFILE=default           # "default" | "reaction_heavy" | "payoff_heavy"
# 길이 정책 (LengthPolicy)
LENGTH_MIN_WINDOW_SEC=30.0        # 탐색 윈도우 최소
LENGTH_MAX_WINDOW_SEC=180.0       # 탐색 윈도우 최대
LENGTH_MAX_2SPAN_SEC=64.0         # 2-span 코어 합산 상한
LENGTH_MAX_3SPAN_SEC=90.0         # 3-span 코어 합산 상한
LENGTH_RENDER_TARGET_MIN_SEC=30.0 # 렌더 타깃 최소
LENGTH_RENDER_TARGET_MAX_SEC=75.0 # 렌더 타깃 최대
LENGTH_RENDER_IDEAL_SEC=50.0      # 렌더 타깃 이상값

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

### CandidateFeedback Schema

```python
class CandidateFeedback(Base):
    __tablename__ = "candidate_feedbacks"

    id: Mapped[str]                    # UUID PK
    candidate_id: Mapped[str]          # FK → candidates.id
    created_seq: Mapped[int | None]    # 삽입 순서 보장용 auto-increment (nullable, migration 0006)
    action: Mapped[str]                # FeedbackAction: selected|rejected|edited|reordered
    reason: Mapped[str | None]
    failure_tags: Mapped[list[str]]    # JSON — Candidate.failure_tags와 동기화
    before_snapshot: Mapped[dict]      # 변경 전 상태 {status, selected, candidate_index, total_score, failure_tags}
    after_snapshot: Mapped[dict]       # 변경 후 상태 (동일 키)
    metadata_json: Mapped[dict]       # reorder_from/to/count, episode_selected_count 등
    created_at: Mapped[datetime]
```

### Canonical `feedback_summary` Shape

```python
class CandidateFeedbackSummary(BaseModel):
    feedback_count: int = 0
    latest_feedback_action: str | None = None
    latest_feedback_at: datetime | None = None
    latest_feedback_reason: str | None = None
```

**latest feedback 선택 기준:** `created_seq DESC NULLS LAST, created_at DESC`

> `created_seq`는 DB-native sequence가 아닌 `max(created_seq)+1` + retry-on-conflict 방식이다. 내부 운영툴/저동시성 환경에서는 충분하지만, 고동시성 확장 시 DB-native sequence 또는 autoincrement 전환을 검토할 수 있다.

**`failure_tags` 동기화 정책:**
- 피드백 생성 시 `failure_tags` 필드는 항상 존재 (`default_factory=list`)
- `[]` → Candidate.failure_tags clear, `["tag", ...]` → overwrite+dedupe
- 키 미전송 → default `[]` → clear (기존 태그를 보존하지 않음)
- 레거시 `created_seq=NULL` 행은 `created_at DESC`로 fallback 정렬

### 상태 변경 API 정책

| 경로 | 동작 | 피드백 기록 |
|------|------|------------|
| `POST /candidates/{id}/feedbacks` | 상태 변경 + 피드백 로그 | ✅ 기록됨 (권장 경로) |
| `POST /candidates/{id}/select` | 상태 변경만 | ❌ 기록 안 됨 (레거시 호환) |
| `POST /candidates/{id}/reject` | 상태 변경만 | ❌ 기록 안 됨 (레거시 호환) |

> `/select`와 `/reject`는 기존 API 호환을 위해 유지하지만, audit trail이 필요한 운영 환경에서는 `/feedbacks` 경로 사용을 권장한다.

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
| 0005_candidate_feedback | `candidate_feedbacks` 테이블 생성, `candidates.failure_tags` JSON 컬럼 추가 |
| 0006_feedback_created_seq | `candidate_feedbacks.created_seq` nullable integer 컬럼 추가 (deterministic latest 선택용) |

---

### D.4 설정 및 환경변수

**파일:** `backend/app/core/config.py`, `backend/.env.example`

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `DATABASE_URL` | `sqlite:///data/app.db` | PostgreSQL 또는 SQLite |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis URL |
| `CELERY_TASK_ALWAYS_EAGER` | `True` | True = 동기 실행 (테스트용) |
| `OPENAI_API_KEY` | `""` | 없으면 Mock 폴백 |
| `OPENAI_MODEL` | `"gpt-5.1"` | 스크립트 생성 모델 |
| `ALLOW_MOCK_LLM_FALLBACK` | `True` | OpenAI 실패 시 결정적 Mock |
| `VISION_CANDIDATE_RERANK` | `True` | GPT-4 Vision 재랭크 활성화 |
| `VISION_MAX_CANDIDATES_PER_EPISODE` | `8` | Vision 적용 최대 후보 수 |
| `VISION_MAX_FRAMES_PER_CANDIDATE` | `6` | 후보당 최대 프레임 수 |
| `VISION_MODEL` | `"gpt-5.1"` | Vision 재랭크 모델 |
| `VISION_PROMPT_VERSION` | `"vision_candidate_rerank_v2"` | 프롬프트 버전 (한국어 v2) |
| `FFMPEG_SCENE_THRESHOLD` | `0.32` | FFmpeg scene 감지 임계값 |
| `ASR_ENABLED` | `False` | Whisper ASR 활성화 |
| `WHISPER_MODEL_SIZE` | `"medium"` | Whisper 모델 크기 |
| `WHISPER_PREFER_FASTER` | `True` | faster-whisper 우선 시도 |
| `DEFAULT_LANGUAGE` | `"ko"` | ASR 기본 언어 |
| `AUDIO_ANALYSIS_BACKEND` | `"ffmpeg"` | 오디오 분석 백엔드 |
| `AUDIO_LIBROSA_ENABLED` | `False` | librosa 고급 분석 활성화 |
| `EMBEDDING_SIGNALS_ENABLED` | `False` | ML 임베딩 언어 시그널 |
| `LLM_ARC_JUDGE_ENABLED` | `False` | LLM Arc Judge 활성화 |
| `LLM_ARC_JUDGE_TOP_K` | `5` | Arc Judge 적용 최대 후보 수 |
| `SCORING_PROFILE` | `"default"` | 스코어링 프로파일 |
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

**임베딩 기반 EmbeddingSignals — `score_window()` live path (`EMBEDDING_SIGNALS_ENABLED` feature flag):**
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

**`generate_audio_seeds_live()` — Track C 단일 진입점:**

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

#### D.7.4 스코어링 — 실제 예시 (60초 QA 패턴 후보)

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

#### D.7.5 Arc 재랭크 델타 공식

```python
# candidate_rerank.py — _evaluate_arc_quality()
arc_quality = (
    setup_strength          * 0.15
    + payoff_strength       * 0.25
    + setup_to_payoff_delta * 0.15
    + arc_continuity        * 0.10
    + standalone            * 0.15
    + visual_audio_impact   * 0.05
    + length_fit            * 0.05   # 이상적 길이 30~75초
    - context_penalty               # max(0, avg_ctx_dep - 0.35) * 0.6
    - payoff_weakness_penalty       # 0.15 if payoff < 0.15 and setup >= 0.2
)
arc_quality_delta = clamp((arc_quality - 0.3) * 3.0, -1.5, 1.5)
# final_score = clamp(old_score + delta, 1.0, 10.0)
```

---

### D.8 콘텐츠 생성 서비스

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

---

### D.9 API 엔드포인트 전체

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

### D.10 프론트엔드 구조

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

### D.11 스모크 테스트

**파일:** `backend/scripts/smoke_test.py`

```bash
ffmpeg -f lavfi -i "color=black:s=1920x1080:r=25" \
       -f lavfi -i "sine=frequency=440:sample_rate=44100" \
       -t 18 -c:v libx264 -crf 23 -c:a aac -b:a 128k sample.mp4
```

테스트 시퀀스: 단위 테스트(tone signals, QA 패턴, IOU 중복 제거) → 통합 테스트(POST /episodes ~ GET /exports/{id}) → 임베딩 disabled/no-key 폴백 검증(Tests 18–22) → audio_path=None 생존 검증.

---

### D.12 스토리지 레이아웃

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

### D.13 메타데이터 JSON 구조

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

### D.14 설계 제약값

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
- **YouTube/SNS 자동 업로드** — out of scope, 타당성 조사 후 결정 (할당량 제한: ~6건/일)
- **Speaker Diarization** — out of scope, pyannote.audio 의존성 큼, 필요성 검증 후 도입 결정

#### 코드 내 주요 주석

- `config.py`: `CANDIDATE_RERANK_LLM` 레거시 플래그 — `VISION_CANDIDATE_RERANK=True` 또는 이 플래그 중 하나만 켜도 Vision 재랭크 활성화 (`vision_rerank_enabled` 프로퍼티)
- `candidate_rerank.py`: `llm_arc_judge()`는 구현됨. `LLM_ARC_JUDGE_ENABLED=False`(기본값)이면 조용히 스킵
- `asr_service.py`: `ASR_ENABLED=False`(기본값). 활성화 시 faster-whisper → openai-whisper 순 폴백

---

*작성 기준: 2026-03-31 / 본문 기준 커밋 `0b6d186`*
