from __future__ import annotations

import logging
import math
import re
from collections import Counter
from typing import TypedDict

logger = logging.getLogger(__name__)

KO_COMEDY_KEYWORDS = (
    "웃",
    "웃기",
    "웃겨",
    "농담",
    "장난",
    "유머",
    "재밌",
    "코미디",
    "하하",
    "ㅋㅋ",
    "미친",
    "황당",
    "바보",
    "말도 안",
)
EN_COMEDY_KEYWORDS = (
    "funny",
    "hilarious",
    "ridiculous",
    "insane",
    "crazy",
    "awkward",
    "joke",
    "kidding",
    "idiot",
    "moron",
    "seriously",
    "what",
    "no way",
    "unbelievable",
    "damn",
)
KO_EMOTION_KEYWORDS = (
    "감동",
    "눈물",
    "울",
    "울컥",
    "미안",
    "고마",
    "사랑",
    "마음",
    "아프",
    "슬프",
    "그리",
    "후회",
    "용서",
    "가족",
    "엄마",
    "아빠",
    "죽",
    "이별",
)
EN_EMOTION_KEYWORDS = (
    "sorry",
    "love",
    "miss",
    "hurt",
    "family",
    "cry",
    "heart",
    "leave",
    "goodbye",
    "please",
    "thank you",
    "forgive",
    "regret",
    "sad",
    "pain",
)
SURPRISE_KEYWORDS = (
    "what",
    "wait",
    "no",
    "oh my god",
    "seriously",
    "really",
    "설마",
    "진짜",
    "뭐",
    "왜",
    "말도 안",
)
TENSION_KEYWORDS = (
    "stop",
    "dont",
    "can't",
    "cant",
    "must",
    "now",
    "why",
    "하지 마",
    "안 돼",
    "당장",
    "지금",
    "왜",
)
PAYOFF_KEYWORDS = (
    "so",
    "then",
    "thats why",
    "that's why",
    "see",
    "told you",
    "그러니까",
    "그래서",
    "봐",
    "거봐",
    "내가 그랬지",
)
REACTION_KEYWORDS = (
    "really",
    "seriously",
    "no way",
    "what",
    "oh",
    "uh",
    "huh",
    "진짜",
    "뭐야",
    "헐",
    "어이없",
    "말도 안",
    "설마",
)
QUESTION_MARKERS = ("?", "why", "what", "how", "who", "where", "when", "무슨", "왜", "누구", "어떻게", "뭐")
ANSWER_MARKERS = (
    "yes",
    "yeah",
    "no",
    "because",
    "thats why",
    "that's why",
    "그래",
    "아니",
    "왜냐",
    "그러니까",
    "맞아",
)
TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣']{2,}")


class ToneSignals(TypedDict):
    comedy_signal: float
    emotion_signal: float
    surprise_signal: float
    tension_signal: float
    reaction_signal: float
    payoff_signal: float
    question_signal: float


def normalize_text(value: str) -> str:
    cleaned = value.lower().replace("\n", " ").replace("’", "'")
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"[^0-9a-z가-힣' ]+", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def extract_tokens(value: str) -> list[str]:
    """Dedupe용 unique token 목록. jaccard similarity 등에 사용."""
    text = normalize_text(value)
    if not text:
        return []
    tokens = [token for token in TOKEN_RE.findall(text) if len(token) >= 2]
    seen: set[str] = set()
    out: list[str] = []
    for token in tokens:
        if token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out


def extract_token_stream(value: str) -> list[str]:
    """중복 제거하지 않은 raw token sequence. 빈도 기반 entity 계산에 사용."""
    text = normalize_text(value)
    if not text:
        return []
    return [token for token in TOKEN_RE.findall(text) if len(token) >= 2]


def detect_language_hint(value: str) -> str:
    if not value.strip():
        return "unknown"
    hangul_count = len(re.findall(r"[가-힣]", value))
    latin_count = len(re.findall(r"[A-Za-z]", value))
    if hangul_count and latin_count:
        return "mixed"
    if hangul_count:
        return "ko"
    if latin_count:
        return "en"
    return "unknown"


# 대명사 및 공통 조사·접속사 stop words (entity로 오인 방지)
_PRONOUN_STOP: frozenset[str] = frozenset({
    # 한국어 대명사 / 지시어
    "그", "그녀", "그들", "그것", "저", "저것", "저들",
    "나", "너", "우리", "여러분", "이것", "그거", "저거",
    "이거", "거기", "여기", "저기", "이분", "그분",
    # 영어 대명사
    "he", "she", "they", "it", "we", "you", "i", "me",
    "him", "her", "them", "us", "his", "its", "our", "your",
    # 흔한 동사/형용사 파편
    "있", "없", "하", "됩", "됐", "했", "합", "해",
    "know", "think", "said", "just", "like", "dont", "cant",
})


def dominant_entities(tokens: list[str], *, limit: int = 5) -> list[str]:
    """빈도 기반 dominant entity 추출.

    raw token stream(중복 포함)을 입력으로 받아야 정확하다.
    대명사·지시어·조사 파편은 stop_words로 필터링한다.
    """
    counts = Counter(
        token
        for token in tokens
        if len(token) >= 2 and token not in _PRONOUN_STOP
    )
    return [token for token, _ in counts.most_common(limit)]


def _keyword_signal_score(text: str, keywords: tuple[str, ...]) -> float:
    normalized = normalize_text(text)
    if not normalized:
        return 0.0
    hits = sum(1 for keyword in keywords if normalize_text(keyword) in normalized)
    punctuation_bonus = 0.0
    if "!" in text:
        punctuation_bonus += 0.15
    if "?" in text:
        punctuation_bonus += 0.12
    if re.search(r"[!?]{2,}", text):
        punctuation_bonus += 0.12
    uppercase_tokens = [part for part in re.findall(r"\b[A-Z]{2,}\b", text) if len(part) >= 2]
    if uppercase_tokens:
        punctuation_bonus += 0.08
    return min(1.0, hits * 0.2 + punctuation_bonus)


def tone_signals(text: str) -> ToneSignals:
    normalized = normalize_text(text)
    question_signal = 0.0
    if "?" in text:
        question_signal += 0.4
    if any(marker in normalized for marker in QUESTION_MARKERS):
        question_signal += 0.35
    question_signal = min(1.0, question_signal)
    return {
        "comedy_signal": max(
            _keyword_signal_score(text, KO_COMEDY_KEYWORDS),
            _keyword_signal_score(text, EN_COMEDY_KEYWORDS),
        ),
        "emotion_signal": max(
            _keyword_signal_score(text, KO_EMOTION_KEYWORDS),
            _keyword_signal_score(text, EN_EMOTION_KEYWORDS),
        ),
        "surprise_signal": _keyword_signal_score(text, SURPRISE_KEYWORDS),
        "tension_signal": _keyword_signal_score(text, TENSION_KEYWORDS),
        "reaction_signal": _keyword_signal_score(text, REACTION_KEYWORDS),
        "payoff_signal": _keyword_signal_score(text, PAYOFF_KEYWORDS),
        "question_signal": question_signal,
    }


def answer_marker_score(text: str) -> float:
    normalized = normalize_text(text)
    score = 0.0
    if any(marker in normalized for marker in ANSWER_MARKERS):
        score += 0.55
    if normalized.startswith(("yes", "yeah", "no", "그래", "아니")):
        score += 0.25
    return min(1.0, score)


# ---------------------------------------------------------------------------
# ML 기반 임베딩 유사도 시그널
# ---------------------------------------------------------------------------

# 각 톤 카테고리의 레퍼런스 문장 (임베딩 앵커)
_EMBEDDING_ANCHORS: dict[str, list[str]] = {
    "comedy": [
        "완전 웃긴 상황이야, 이게 말이 돼?",
        "황당하고 어이없어서 웃음이 나온다",
        "이 사람 진짜 웃겨, 코미디야 완전",
    ],
    "emotion": [
        "너무 감동받아서 눈물이 났어",
        "미안해, 정말 미안해. 사랑해",
        "가족이 생각나서 눈물이 흘렀다",
    ],
    "tension": [
        "지금 당장 멈춰, 하지 마!",
        "안 돼, 절대로 그러면 안 돼",
        "위험해, 빨리 도망쳐야 해",
    ],
    "reaction": [
        "헐, 이게 진짜야? 말도 안 돼",
        "뭐야 이거, 진짜 충격이다",
        "설마 진짜로 그런 건 아니겠지",
    ],
    "payoff": [
        "그러니까 내가 맞았잖아, 거봐",
        "결국 이렇게 됐네, 그래서 그랬구나",
        "마침내 밝혀졌다, 이게 진실이었어",
    ],
}


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """두 벡터의 코사인 유사도 (-1 ~ 1)."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _mean_vector(vectors: list[list[float]]) -> list[float]:
    if not vectors:
        return []
    dim = len(vectors[0])
    result: list[float] = [0.0] * dim
    for vec in vectors:
        for i, v in enumerate(vec):
            result[i] += v
    n = float(len(vectors))
    return [x / n for x in result]


def _get_embeddings_batch(texts: list[str], api_key: str, model: str) -> list[list[float]]:
    """OpenAI Embeddings API를 호출해 벡터 목록을 반환한다."""
    from openai import OpenAI  # optional dependency
    client = OpenAI(api_key=api_key)
    response = client.embeddings.create(model=model, input=texts)
    return [item.embedding for item in sorted(response.data, key=lambda x: x.index)]


class EmbeddingSignals(TypedDict):
    comedy_emb: float
    emotion_emb: float
    tension_emb: float
    reaction_emb: float
    payoff_emb: float
    embedding_used: bool


def compute_embedding_signals(
    text: str,
    *,
    api_key: str | None = None,
    model: str = "text-embedding-3-small",
) -> EmbeddingSignals:
    """텍스트의 임베딩 기반 톤 시그널을 계산한다.

    OpenAI API 키가 없거나 호출 실패 시 키워드 기반 폴백으로 자동 전환한다.

    Returns:
        EmbeddingSignals: 각 카테고리 유사도 (0~1) + embedding_used 플래그
    """
    fallback = _embedding_fallback(text)
    if not api_key or not text.strip():
        return fallback

    try:
        # 레퍼런스 앵커 + 쿼리 텍스트를 한 번에 배치 요청
        anchor_texts: list[str] = []
        category_order: list[str] = list(_EMBEDDING_ANCHORS.keys())
        for cat in category_order:
            anchor_texts.extend(_EMBEDDING_ANCHORS[cat])
        query_idx = len(anchor_texts)
        all_texts = anchor_texts + [text[:2000]]  # API 토큰 제한 고려

        vectors = _get_embeddings_batch(all_texts, api_key, model)
        query_vec = vectors[query_idx]

        offset = 0
        similarities: dict[str, float] = {}
        for cat in category_order:
            n = len(_EMBEDDING_ANCHORS[cat])
            cat_vecs = vectors[offset: offset + n]
            anchor_vec = _mean_vector(cat_vecs)
            sim = _cosine_similarity(query_vec, anchor_vec)
            # 코사인 유사도 [−1, 1] → [0, 1] 정규화 후 클리핑
            similarities[cat] = max(0.0, min(1.0, (sim + 1.0) / 2.0))
            offset += n

        return {
            "comedy_emb": round(similarities.get("comedy", 0.0), 4),
            "emotion_emb": round(similarities.get("emotion", 0.0), 4),
            "tension_emb": round(similarities.get("tension", 0.0), 4),
            "reaction_emb": round(similarities.get("reaction", 0.0), 4),
            "payoff_emb": round(similarities.get("payoff", 0.0), 4),
            "embedding_used": True,
        }
    except Exception as exc:
        logger.debug("임베딩 시그널 계산 실패 — 키워드 폴백: %s", exc)
        return fallback


def _embedding_fallback(text: str) -> EmbeddingSignals:
    """OpenAI 없이 키워드 기반으로 임베딩 시그널을 근사한다."""
    ts = tone_signals(text)
    return {
        "comedy_emb": round(ts["comedy_signal"], 4),
        "emotion_emb": round(ts["emotion_signal"], 4),
        "tension_emb": round(ts["tension_signal"], 4),
        "reaction_emb": round(ts["reaction_signal"], 4),
        "payoff_emb": round(ts["payoff_signal"], 4),
        "embedding_used": False,
    }
