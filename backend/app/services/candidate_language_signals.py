from __future__ import annotations

import re
from collections import Counter
from typing import TypedDict

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


def dominant_entities(tokens: list[str], *, limit: int = 5) -> list[str]:
    """빈도 기반 dominant entity 추출. raw token stream(중복 포함)을 입력으로 받아야 정확하다."""
    counts = Counter(token for token in tokens if len(token) >= 3)
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
