"""Entity 추출 서비스.

candidate_language_signals.py의 단순 빈도 기반 dominant_entities를 보완한다.
규칙 기반 NER로 한국어 인물명·직함 패턴을 우선 추출하고,
대명사/지시어를 stop_words로 필터링한다.
"""

from __future__ import annotations

import re
from collections import Counter

# 한국어 인물명 패턴 (2~4글자 한글 + 직함/호칭 접미사)
_KO_PERSON_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"[가-힣]{2,4}(?:씨|님|군|양|선생|교수|대리|과장|부장|팀장|사장|회장|원장|의원|감독|작가)"),
    re.compile(r"[가-힣]{2,4}(?:이라고|이라는|라고|라는)"),  # 호명 패턴
]

# 영문 인물명 패턴 (First Last / First)
_EN_PERSON_PATTERN = re.compile(r"\b[A-Z][a-z]{1,12}(?:\s[A-Z][a-z]{1,12})?\b")

# 자막에서 화자 레이블 추출 패턴 (예: "[이준혁]: ..." or "이준혁: ...")
_SPEAKER_LABEL_PATTERN = re.compile(r"^\[?([가-힣A-Za-z]{2,10})\]?\s*:")


def extract_named_entities_rule_based(text: str) -> list[str]:
    """규칙 기반으로 한국어 인물명·직함 패턴을 추출한다.

    Args:
        text: 자막/대사 텍스트

    Returns:
        추출된 entity 목록 (중복 제거, 순서 유지)
    """
    found: list[str] = []
    for pattern in _KO_PERSON_PATTERNS:
        found.extend(pattern.findall(text))
    found.extend(_EN_PERSON_PATTERN.findall(text))

    # 중복 제거 (순서 유지)
    seen: set[str] = set()
    result: list[str] = []
    for ent in found:
        key = ent.strip()
        if key and key not in seen:
            seen.add(key)
            result.append(key)
    return result


def extract_speaker_labels(text: str) -> list[str]:
    """자막 텍스트에서 '[화자명]:' 또는 '화자명:' 패턴으로 화자를 추출한다.

    Args:
        text: 자막/대사 텍스트 (멀티라인 가능)

    Returns:
        화자명 목록 (중복 제거)
    """
    labels: list[str] = []
    for line in text.splitlines():
        m = _SPEAKER_LABEL_PATTERN.match(line.strip())
        if m:
            labels.append(m.group(1).strip())
    # 중복 제거 순서 유지
    seen: set[str] = set()
    result: list[str] = []
    for label in labels:
        if label not in seen:
            seen.add(label)
            result.append(label)
    return result


def enhanced_dominant_entities(
    text: str,
    token_stream: list[str],
    *,
    limit: int = 8,
) -> list[str]:
    """규칙 기반 NER + 빈도 기반 entity 추출을 결합한다.

    1. 화자 레이블 → 가장 신뢰도 높음, 우선 포함
    2. 규칙 기반 인물명 패턴 → 두 번째 우선순위
    3. 빈도 기반 토큰 (stop_words 필터 적용) → 나머지 채우기

    Args:
        text: 원본 텍스트 (화자 레이블·인물명 패턴 추출용)
        token_stream: 중복 포함 raw token stream (빈도 계산용)
        limit: 최대 반환 entity 수

    Returns:
        entity 목록 (최대 limit개)
    """
    from app.services.candidate_language_signals import _PRONOUN_STOP

    result: list[str] = []
    seen: set[str] = set()

    def _add(ent: str) -> None:
        key = ent.strip()
        if key and key not in seen and len(key) >= 2:
            seen.add(key)
            result.append(key)

    # 1. 화자 레이블
    for label in extract_speaker_labels(text):
        _add(label)

    # 2. 규칙 기반 NER
    for ent in extract_named_entities_rule_based(text):
        _add(ent)

    # 3. 빈도 기반 보충
    if len(result) < limit:
        freq = Counter(
            token
            for token in token_stream
            if len(token) >= 2 and token not in _PRONOUN_STOP
        )
        for token, _ in freq.most_common(limit * 2):
            if len(result) >= limit:
                break
            _add(token)

    return result[:limit]
