from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import TranscriptSegment
from app.services.storage_service import episode_root

IMPORTED_ASS = "imported_subs.ass"
IMPORTED_VTT = "imported_subs.vtt"
EDITED_ASS = "edited_subs.ass"
GENERATED_ASS = "clip_subs.ass"


def transcript_segments_for_clip(
    db: Session, episode_id: str, clip_start: float, clip_end: float
) -> list[TranscriptSegment]:
    q = (
        select(TranscriptSegment)
        .where(TranscriptSegment.episode_id == episode_id)
        .where(TranscriptSegment.start_time <= clip_end)
        .where(TranscriptSegment.end_time >= clip_start)
        .order_by(TranscriptSegment.start_time.asc())
    )
    return list(db.scalars(q))


def candidate_subtitle_dir(episode_id: str, candidate_id: str) -> Path:
    return episode_root(episode_id) / "candidates" / candidate_id


def edited_ass_path(episode_id: str, candidate_id: str) -> Path:
    return candidate_subtitle_dir(episode_id, candidate_id) / EDITED_ASS


def read_candidate_edited_ass(episode_id: str, candidate_id: str) -> str | None:
    path = edited_ass_path(episode_id, candidate_id)
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def write_candidate_edited_ass(episode_id: str, candidate_id: str, content: str) -> Path:
    out_dir = candidate_subtitle_dir(episode_id, candidate_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / EDITED_ASS
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    path.write_text(normalized, encoding="utf-8")
    return path


def delete_candidate_edited_ass(episode_id: str, candidate_id: str) -> None:
    edited_ass_path(episode_id, candidate_id).unlink(missing_ok=True)


def find_imported_subtitle_file(out_dir: Path) -> Path | None:
    for name in (IMPORTED_ASS, IMPORTED_VTT):
        p = out_dir / name
        if p.is_file():
            return p
    return None


def _vtt_ts(sec: float) -> str:
    ms_total = max(0, int(round(float(sec) * 1000)))
    h, ms_total = divmod(ms_total, 3600000)
    m, ms_total = divmod(ms_total, 60000)
    s, ms = divmod(ms_total, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def _vtt_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;")


def build_webvtt_for_clip(
    segments: list[TranscriptSegment],
    clip_start: float,
    clip_end: float,
    text_overrides: dict[str, str] | None = None,
) -> str:
    """쇼츠 클립(0초=트림 시작) 기준 상대 타임코드."""
    overrides = text_overrides or {}
    lines = ["WEBVTT", ""]
    cues: list[tuple[float, float, str]] = []
    for seg in segments:
        seg_s = max(seg.start_time, clip_start)
        seg_e = min(seg.end_time, clip_end)
        if seg_e <= seg_s:
            continue
        rel_s = seg_s - clip_start
        rel_e = seg_e - clip_start
        raw = overrides.get(seg.id, seg.text)
        t = " ".join(raw.replace("\r", " ").split())
        cues.append((rel_s, rel_e, _vtt_escape(t) or " "))

    for i, (a, b, text) in enumerate(cues):
        lines.append(str(i + 1))
        lines.append(f"{_vtt_ts(a)} --> {_vtt_ts(b)}")
        lines.append(text)
        lines.append("")
    return "\n".join(lines)


def build_webvtt_absolute_for_range(
    segments: list[TranscriptSegment],
    range_start: float,
    range_end: float,
    text_overrides: dict[str, str] | None = None,
) -> str:
    """원본 영상 타임라인(절대 초) — 브라우저 `<video>` + `<track>` 미리보기용."""
    overrides = text_overrides or {}
    lines = ["WEBVTT", ""]
    cues: list[tuple[float, float, str]] = []
    for seg in segments:
        seg_s = max(seg.start_time, range_start)
        seg_e = min(seg.end_time, range_end)
        if seg_e <= seg_s:
            continue
        raw = overrides.get(seg.id, seg.text)
        t = " ".join(raw.replace("\r", " ").split())
        cues.append((seg_s, seg_e, _vtt_escape(t) or " "))

    for i, (a, b, text) in enumerate(cues):
        lines.append(str(i + 1))
        lines.append(f"{_vtt_ts(a)} --> {_vtt_ts(b)}")
        lines.append(text)
        lines.append("")
    return "\n".join(lines)


def _ass_ts(sec: float) -> str:
    cs_total = max(0, int(round(float(sec) * 100)))
    h, cs_total = divmod(cs_total, 360000)
    m, cs_total = divmod(cs_total, 6000)
    s, cs = divmod(cs_total, 100)
    return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"


def _ass_escape(text: str) -> str:
    return text.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}").replace("\n", r"\N")


def _normalize_hex_color(value: str | None, default: str) -> str:
    raw = (value or "").strip()
    if raw.startswith("#"):
        raw = raw[1:]
    if len(raw) == 3:
        raw = "".join(ch * 2 for ch in raw)
    if len(raw) != 6:
        return default
    try:
        int(raw, 16)
    except ValueError:
        return default
    return raw.upper()


def _hex_to_ass_color(value: str | None, *, default: str, alpha: str = "00") -> str:
    hex_color = _normalize_hex_color(value, default)
    rr = hex_color[0:2]
    gg = hex_color[2:4]
    bb = hex_color[4:6]
    return f"&H{alpha}{bb}{gg}{rr}"


def build_ass_for_clip(
    segments: list[TranscriptSegment],
    clip_start: float,
    clip_end: float,
    style: dict[str, Any] | None = None,
    text_overrides: dict[str, str] | None = None,
) -> str:
    st = style or {}
    font_family = str(st.get("font_family") or "Noto Sans CJK KR")
    fs = int(st.get("font_size", 28))
    al = int(st.get("alignment", 2))
    mv = int(st.get("margin_v", 52))
    ol = int(st.get("outline", 2))
    shadow = int(st.get("shadow", 0))
    bold = -1 if st.get("bold") else 0
    primary_colour = _hex_to_ass_color(
        st.get("primary_color"),
        default="FFFFFF",
    )
    outline_colour = _hex_to_ass_color(
        st.get("outline_color"),
        default="000000",
    )
    background_box = bool(st.get("background_box"))
    border_style = 3 if background_box else 1
    back_colour = _hex_to_ass_color(
        "#000000",
        default="000000",
        alpha="80" if background_box else "00",
    )

    overrides = text_overrides or {}
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "WrapStyle: 0",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        (
            "Style: Default,"
            f"{font_family},{fs},{primary_colour},&H000000FF,{outline_colour},{back_colour},"
            f"{bold},0,0,0,100,100,0,0,{border_style},{ol},{shadow},{al},20,20,{mv},1"
        ),
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for seg in segments:
        seg_s = max(seg.start_time, clip_start)
        seg_e = min(seg.end_time, clip_end)
        if seg_e <= seg_s:
            continue
        rel_s = seg_s - clip_start
        rel_e = seg_e - clip_start
        raw = overrides.get(seg.id, seg.text)
        txt = " ".join(raw.replace("\r", " ").replace("\n", " ").split()).strip() or " "
        lines.append(
            f"Dialogue: 0,{_ass_ts(rel_s)},{_ass_ts(rel_e)},Default,,0,0,0,,{_ass_escape(txt)}"
        )
    return "\n".join(lines)
