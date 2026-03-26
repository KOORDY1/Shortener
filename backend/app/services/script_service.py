from __future__ import annotations

import json
from typing import Any

from openai import OpenAI
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Candidate, CandidateStatus, ScriptDraft, TranscriptSegment
from app.services.analysis_service import candidate_segments


settings = get_settings()


def build_prompt_context(candidate: Candidate, transcript_segments: list[TranscriptSegment]) -> str:
    transcript_text = "\n".join(
        f"- [{segment.start_time:.1f}-{segment.end_time:.1f}] {segment.text}"
        for segment in transcript_segments
    )
    scores = json.dumps(candidate.scores_json or {}, ensure_ascii=False)
    return (
        f"Candidate type: {candidate.type}\n"
        f"Candidate title hint: {candidate.title_hint}\n"
        f"Time range: {candidate.start_time:.1f}s - {candidate.end_time:.1f}s\n"
        f"Scores: {scores}\n"
        "Transcript segments:\n"
        f"{transcript_text}"
    )


def clean_json_text(raw_text: str) -> str:
    stripped = raw_text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[1]
        stripped = stripped.rsplit("```", 1)[0]
    return stripped.strip()


def fallback_drafts(
    candidate: Candidate, language: str, versions: int, channel_style: str
) -> list[dict[str, Any]]:
    drafts: list[dict[str, Any]] = []
    for index in range(versions):
        hook = (
            f"{candidate.title_hint}."
            if language == "en"
            else f"이 장면이 바로 포인트입니다: {candidate.title_hint}"
        )
        body = (
            "The scene lands because the dialogue sounds controlled while the tension keeps rising."
            if language == "en"
            else "겉으로는 차분한데 실제로는 긴장이 계속 올라가는 대사라서 해설형 쇼츠로 잘 먹힙니다."
        )
        cta = (
            "Follow for more commentary-ready drama moments."
            if language == "en"
            else f"{channel_style} 톤으로 이런 장면을 더 보고 싶다면 다음 후보도 확인해 보세요."
        )
        drafts.append(
            {
                "hook": hook,
                "body": f"{body} 버전 {index + 1}에서는 훅과 설명의 강도를 조금 다르게 잡았습니다.",
                "cta": cta,
                "title_options": [
                    candidate.title_hint,
                    f"{candidate.title_hint} version {index + 1}",
                    "The line that changes the whole scene"
                    if language == "en"
                    else "한마디로 분위기가 바뀌는 장면",
                ],
            }
        )
    return drafts


def classify_fallback_reason(exc: Exception) -> str:
    message = str(exc).lower()
    exc_name = exc.__class__.__name__.lower()
    if "openai_api_key" in message or "api key" in message:
        return "missing_openai_api_key"
    if "ratelimit" in exc_name or "rate limit" in message or "429" in message:
        return "rate_limited"
    if "json" in message or "drafts array" in message or "parse" in message:
        return "openai_response_parse_failed"
    if "timeout" in exc_name or "timeout" in message:
        return "openai_timeout"
    return "openai_request_failed"


def generate_openai_drafts(
    *,
    candidate: Candidate,
    transcript_segments: list[TranscriptSegment],
    language: str,
    versions: int,
    tone: str,
    channel_style: str,
) -> list[dict[str, Any]]:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    client = OpenAI(api_key=settings.openai_api_key)
    prompt = build_prompt_context(candidate, transcript_segments)
    response = client.chat.completions.create(
        model=settings.openai_model,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": (
                    "You generate structured shorts scripts. "
                    "Return strict JSON with a top-level 'drafts' array. "
                    "Each draft must contain 'hook', 'body', 'cta', and 'title_options'. "
                    "Each title_options value must be a list of 3 concise titles."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Create {versions} script drafts in language={language}, tone={tone}, "
                    f"channel_style={channel_style}.\n"
                    "Keep each draft concise, commentary-first, and ready for direct UI rendering.\n"
                    f"{prompt}"
                ),
            },
        ],
    )
    content = response.choices[0].message.content or ""
    parsed = json.loads(clean_json_text(content))
    drafts = parsed.get("drafts", [])
    if not isinstance(drafts, list) or not drafts:
        raise ValueError("OpenAI response did not contain a valid drafts array")
    return drafts


def generate_draft_payloads(
    *,
    candidate: Candidate,
    transcript_segments: list[TranscriptSegment],
    language: str,
    versions: int,
    tone: str,
    channel_style: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    try:
        drafts = generate_openai_drafts(
            candidate=candidate,
            transcript_segments=transcript_segments,
            language=language,
            versions=versions,
            tone=tone,
            channel_style=channel_style,
        )
        return drafts[:versions], {"provider": "openai", "model": settings.openai_model}
    except Exception as exc:
        if not settings.allow_mock_llm_fallback:
            raise
        fallback_reason = classify_fallback_reason(exc)
        return fallback_drafts(candidate, language, versions, channel_style), {
            "provider": "mock",
            "model": settings.openai_model,
            "fallback_reason": fallback_reason,
            "source_error": str(exc)[:500],
        }


def generate_script_drafts_for_candidate(
    db: Session,
    *,
    candidate_id: str,
    language: str,
    versions: int,
    tone: str,
    channel_style: str,
    force_regenerate: bool,
) -> tuple[list[ScriptDraft], dict[str, Any]]:
    candidate = db.get(Candidate, candidate_id)
    if candidate is None:
        raise ValueError("Candidate not found")

    existing = list(
        db.scalars(
            select(ScriptDraft)
            .where(ScriptDraft.candidate_id == candidate_id)
            .order_by(ScriptDraft.version_no.asc())
        )
    )
    if existing and not force_regenerate:
        return existing

    if force_regenerate and existing:
        db.execute(delete(ScriptDraft).where(ScriptDraft.candidate_id == candidate_id))
        db.commit()

    transcript_segments = candidate_segments(db, candidate)
    payloads, generation_meta = generate_draft_payloads(
        candidate=candidate,
        transcript_segments=transcript_segments,
        language=language,
        versions=versions,
        tone=tone,
        channel_style=channel_style,
    )

    created_drafts: list[ScriptDraft] = []
    for index in range(versions):
        source = payloads[index] if index < len(payloads) else payloads[-1]
        hook_text = str(source.get("hook", candidate.title_hint)).strip()
        body_text = str(source.get("body", "")).strip() or candidate.title_hint
        cta_text = str(source.get("cta", "")).strip() or "Check the next candidate."
        title_options = [
            str(item).strip() for item in source.get("title_options", []) if str(item).strip()
        ]
        full_script_text = " ".join(part for part in [hook_text, body_text, cta_text] if part)
        estimated_duration_seconds = round(max(15.0, len(full_script_text) / 12), 2)
        draft_metadata = {
            **generation_meta,
            "tone": tone,
            "channel_style": channel_style,
        }
        draft = ScriptDraft(
            candidate_id=candidate_id,
            version_no=index + 1,
            language=language,
            hook_text=hook_text,
            body_text=body_text,
            cta_text=cta_text,
            full_script_text=full_script_text,
            estimated_duration_seconds=estimated_duration_seconds,
            title_options=title_options[:3] or [candidate.title_hint],
            metadata_json=draft_metadata,
        )
        db.add(draft)
        created_drafts.append(draft)

    candidate.status = CandidateStatus.DRAFTED.value
    db.add(candidate)
    db.commit()

    for draft in created_drafts:
        db.refresh(draft)
    return created_drafts, generation_meta
