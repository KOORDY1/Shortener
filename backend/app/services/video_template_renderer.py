from __future__ import annotations

import shutil
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Candidate, Episode, ScriptDraft, TranscriptSegment, VideoDraft
from app.services.candidate_spans import candidate_clip_spans
from app.services.storage_service import episode_root
from app.services.subtitle_exchange import (
    EDITED_ASS,
    IMPORTED_ASS,
    IMPORTED_VTT,
)
from app.services.subtitle_parse import parse_subtitle_upload_file
from app.services.tts_service import synthesize_short_tts


def _run(cmd: list[str], *, cwd: Path | None = None) -> None:
    completed = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        error = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(error[-4000:] or f"command failed: {' '.join(cmd)}")


def _ffmpeg_filter_path(path: Path) -> str:
    return path.resolve().as_posix().replace(":", r"\:")


def _hex_to_ass_color(value: str, *, alpha: str = "00") -> str:
    raw = value.strip().lstrip("#")
    if len(raw) == 3:
        raw = "".join(ch * 2 for ch in raw)
    if len(raw) != 6:
        raw = "FFFFFF"
    return f"&H{alpha}{raw[4:6]}{raw[2:4]}{raw[0:2]}"


def _ass_ts(sec: float) -> str:
    total = max(0, int(round(sec * 100)))
    hours, total = divmod(total, 360000)
    minutes, total = divmod(total, 6000)
    seconds, centis = divmod(total, 100)
    return f"{hours:d}:{minutes:02d}:{seconds:02d}.{centis:02d}"


def _escape_ass(text: str) -> str:
    return text.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}").replace("\n", r"\N")


def _deep_merge(base: dict[str, Any], override: dict[str, Any] | None) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _clip_text(text: str, *, max_chars: int, line_clamp: int) -> str:
    cleaned = " ".join((text or "").split()).strip()
    if not cleaned:
        return ""
    clipped = cleaned[:max_chars].strip()
    words = clipped.split(" ")
    if line_clamp <= 1 or len(words) <= 1:
        return clipped
    lines: list[str] = []
    current = ""
    target_len = max(8, int(max_chars / max(1, line_clamp)))
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and len(candidate) > target_len and len(lines) < line_clamp - 1:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return "\n".join(lines[:line_clamp])


def _slot_anchor_position(
    anchor: str,
    *,
    width: int,
    height: int,
    top_safe: int,
    bottom_safe: int,
    padding_x: int,
    offset_x: int,
    offset_y: int,
) -> tuple[int, int, int]:
    anchor = anchor or "top-center"
    safe_center_y = top_safe // 2
    bottom_center_y = height - bottom_safe // 2
    if anchor == "top-left":
        return 7, padding_x + offset_x, safe_center_y + offset_y
    if anchor == "top-right":
        return 9, width - padding_x + offset_x, safe_center_y + offset_y
    if anchor == "bottom-left":
        return 1, padding_x + offset_x, bottom_center_y + offset_y
    if anchor == "bottom-right":
        return 3, width - padding_x + offset_x, bottom_center_y + offset_y
    if anchor == "bottom-center":
        return 2, width // 2 + offset_x, bottom_center_y + offset_y
    if anchor == "center":
        return 5, width // 2 + offset_x, height // 2 + offset_y
    return 8, width // 2 + offset_x, safe_center_y + offset_y


def _render_slot_ass(
    slot_name: str,
    slot: dict[str, Any],
    *,
    width: int,
    height: int,
    top_safe: int,
    bottom_safe: int,
    padding_x: int,
) -> tuple[str, str] | None:
    if not slot.get("enabled", True):
        return None
    raw_text = str(slot.get("text") or "").strip()
    if not raw_text:
        return None
    font_size = int(slot.get("font_size") or 36)
    stroke_width = int(slot.get("stroke_width") or 2)
    padding = int(slot.get("padding") or 12)
    max_width = int(slot.get("max_width") or (width - padding_x * 2))
    line_clamp = int(slot.get("line_clamp") or 2)
    max_chars = max(20, int(max_width / max(10.0, font_size * 0.52)))
    text = _clip_text(raw_text, max_chars=max_chars, line_clamp=line_clamp)
    if not text:
        return None

    weight = str(slot.get("font_weight") or "700").lower()
    bold = -1 if weight in {"bold", "700", "800", "900"} else 0
    anchor, pos_x, pos_y = _slot_anchor_position(
        str(slot.get("anchor") or "top-center"),
        width=width,
        height=height,
        top_safe=top_safe,
        bottom_safe=bottom_safe,
        padding_x=padding_x,
        offset_x=int(slot.get("offset_x") or 0),
        offset_y=int(slot.get("offset_y") or 0),
    )
    style_name = f"{slot_name.title().replace('_', '')}Style"
    style_line = (
        "Style: "
        f"{style_name},{slot.get('font_family') or 'Noto Sans CJK KR'},{font_size},"
        f"{_hex_to_ass_color(str(slot.get('color') or '#FFFFFF'))},&H000000FF,"
        f"{_hex_to_ass_color(str(slot.get('stroke_color') or '#000000'))},"
        f"{_hex_to_ass_color(str(slot.get('background_color') or '#000000'), alpha='80')},"
        f"{bold},0,0,0,100,100,0,0,{3 if slot.get('background_color') else 1},"
        f"{stroke_width},{max(0, padding // 6)},{anchor},20,20,20,1"
    )
    event_line = (
        f"Dialogue: 0,{_ass_ts(0)},{_ass_ts(86400)},"
        f"{style_name},,0,0,0,,"
        f"{{\\an{anchor}\\pos({pos_x},{pos_y})}}{_escape_ass(text)}"
    )
    return style_line, event_line


def _build_transcript_events(
    db: Session,
    *,
    episode_id: str,
    clip_start: float,
    clip_end: float,
    offset_sec: float = 0.0,
) -> list[tuple[float, float, str]]:
    segments = list(
        db.scalars(
            select(TranscriptSegment)
            .where(TranscriptSegment.episode_id == episode_id)
            .where(TranscriptSegment.start_time <= clip_end)
            .where(TranscriptSegment.end_time >= clip_start)
            .order_by(TranscriptSegment.start_time.asc())
        )
    )
    events: list[tuple[float, float, str]] = []
    for segment in segments:
        start_time = max(float(segment.start_time), clip_start)
        end_time = min(float(segment.end_time), clip_end)
        if end_time <= start_time:
            continue
        text = " ".join((segment.text or "").replace("\r", " ").split()).strip()
        if not text:
            continue
        events.append((start_time - clip_start + offset_sec, end_time - clip_start + offset_sec, text))
    return events


def _remap_imported_vtt_events(
    cues: list[tuple[float, float, str]],
    *,
    spans: list[dict[str, Any]],
    candidate_start: float,
) -> tuple[list[list[tuple[float, float, str]]], str]:
    total_span_duration = round(
        sum(max(0.0, float(span["end_time"]) - float(span["start_time"])) for span in spans),
        3,
    )
    max_cue_end = max((float(end_time) for _, end_time, _ in cues), default=0.0)
    if max_cue_end <= total_span_duration + 0.5:
        mode = "relative_concat"
    elif max_cue_end <= max(float(span["end_time"]) for span in spans) + 1.0:
        mode = "absolute_episode"
    else:
        mode = "relative_candidate_start"

    remapped: list[list[tuple[float, float, str]]] = []
    concat_cursor = 0.0
    for span in spans:
        span_events: list[tuple[float, float, str]] = []
        span_start = float(span["start_time"])
        span_end = float(span["end_time"])
        span_duration = span_end - span_start
        for cue_start, cue_end, text in cues:
            cue_start = float(cue_start)
            cue_end = float(cue_end)
            if mode == "relative_concat":
                overlap_start = max(cue_start, concat_cursor)
                overlap_end = min(cue_end, concat_cursor + span_duration)
                if overlap_end <= overlap_start:
                    continue
                local_start = overlap_start - concat_cursor
                local_end = overlap_end - concat_cursor
            elif mode == "absolute_episode":
                overlap_start = max(cue_start, span_start)
                overlap_end = min(cue_end, span_end)
                if overlap_end <= overlap_start:
                    continue
                local_start = overlap_start - span_start
                local_end = overlap_end - span_start
            else:
                absolute_start = candidate_start + cue_start
                absolute_end = candidate_start + cue_end
                overlap_start = max(absolute_start, span_start)
                overlap_end = min(absolute_end, span_end)
                if overlap_end <= overlap_start:
                    continue
                local_start = overlap_start - span_start
                local_end = overlap_end - span_start
            span_events.append((round(local_start, 3), round(local_end, 3), text))
        remapped.append(span_events)
        concat_cursor += span_duration
    return remapped, mode


def _build_srt(events: list[tuple[float, float, str]]) -> str:
    def _srt_ts(sec: float) -> str:
        total_ms = max(0, int(round(sec * 1000)))
        hours, total_ms = divmod(total_ms, 3600000)
        minutes, total_ms = divmod(total_ms, 60000)
        seconds, milliseconds = divmod(total_ms, 1000)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

    lines: list[str] = []
    for index, (start_time, end_time, text) in enumerate(events, start=1):
        lines.extend(
            [
                str(index),
                f"{_srt_ts(start_time)} --> {_srt_ts(end_time)}",
                text,
                "",
            ]
        )
    return "\n".join(lines)


def build_default_video_render_config(
    *,
    episode: Episode,
    candidate: Candidate,
    script_draft: ScriptDraft,
    template_type: str,
    burned_caption: bool,
    tts_voice_key: str | None,
) -> dict[str, Any]:
    show_ref = f"{episode.show_title} S{episode.season_number or 1}E{episode.episode_number or 1}"
    return {
        "template_type": template_type or "dramashorts_v1",
        "fit_mode": "contain",
        "background_color": "#111111",
        "content_background_color": "#000000",
        "top_safe_area_height": 240,
        "bottom_safe_area_height": 300,
        "content_padding_x": 28,
        "content_padding_y": 18,
        "subtitle_source": "transcript" if burned_caption else "none",
        "subtitle_style": {
            "font_family": "Noto Sans CJK KR",
            "font_size": 38,
            "alignment": 2,
            "margin_v": 120,
            "outline": 3,
            "primary_color": "#FFFFFF",
            "outline_color": "#000000",
            "shadow": 0,
            "background_box": False,
            "bold": True,
        },
        "text_slots": {
            "top_title": {
                "enabled": True,
                "text": script_draft.hook_text,
                "font_family": "Noto Sans CJK KR",
                "font_size": 60,
                "font_weight": "700",
                "color": "#FFFFFF",
                "stroke_color": "#000000",
                "stroke_width": 3,
                "background_color": "#000000",
                "padding": 14,
                "align": "center",
                "max_width": 920,
                "line_clamp": 2,
                "anchor": "top-center",
                "offset_x": 0,
                "offset_y": 24,
            },
            "bottom_caption": {
                "enabled": True,
                "text": script_draft.body_text[:140],
                "font_family": "Noto Sans CJK KR",
                "font_size": 34,
                "font_weight": "600",
                "color": "#F8F8F8",
                "stroke_color": "#000000",
                "stroke_width": 2,
                "background_color": "#000000",
                "padding": 10,
                "align": "center",
                "max_width": 920,
                "line_clamp": 2,
                "anchor": "bottom-center",
                "offset_x": 0,
                "offset_y": -72,
            },
            "source_label": {
                "enabled": True,
                "text": show_ref,
                "font_family": "Noto Sans CJK KR",
                "font_size": 24,
                "font_weight": "600",
                "color": "#DDDDDD",
                "stroke_color": "#000000",
                "stroke_width": 1,
                "background_color": "",
                "padding": 6,
                "align": "left",
                "max_width": 560,
                "line_clamp": 1,
                "anchor": "bottom-left",
                "offset_x": 24,
                "offset_y": -18,
            },
        },
        "intro_tts_enabled": False,
        "intro_tts_text": script_draft.hook_text,
        "intro_duration_sec": 2.4,
        "outro_tts_enabled": False,
        "outro_tts_text": script_draft.cta_text,
        "outro_duration_sec": 2.2,
        "tts_voice_key": tts_voice_key or "ko_female_01",
        "tts_volume": 1.0,
        "duck_original_audio": False,
    }


def _build_overlay_ass(
    *,
    duration_sec: float,
    width: int,
    height: int,
    top_safe: int,
    bottom_safe: int,
    padding_x: int,
    slot_config: dict[str, Any],
    subtitle_events: list[tuple[float, float, str]],
    subtitle_style: dict[str, Any],
) -> str:
    styles: list[str] = []
    events: list[str] = []
    for slot_name, slot in slot_config.items():
        rendered = _render_slot_ass(
            slot_name,
            slot,
            width=width,
            height=height,
            top_safe=top_safe,
            bottom_safe=bottom_safe,
            padding_x=padding_x,
        )
        if rendered is None:
            continue
        style_line, event_line = rendered
        styles.append(style_line)
        events.append(event_line.replace(_ass_ts(86400), _ass_ts(duration_sec)))

    subtitle_style_line = (
        "Style: Subtitle,"
        f"{subtitle_style.get('font_family') or 'Noto Sans CJK KR'},"
        f"{int(subtitle_style.get('font_size') or 38)},"
        f"{_hex_to_ass_color(str(subtitle_style.get('primary_color') or '#FFFFFF'))},"
        "&H000000FF,"
        f"{_hex_to_ass_color(str(subtitle_style.get('outline_color') or '#000000'))},"
        f"{_hex_to_ass_color('#000000', alpha='00')},"
        f"{-1 if subtitle_style.get('bold') else 0},0,0,0,100,100,0,0,"
        f"{3 if subtitle_style.get('background_box') else 1},"
        f"{int(subtitle_style.get('outline') or 2)},"
        f"{int(subtitle_style.get('shadow') or 0)},"
        f"{int(subtitle_style.get('alignment') or 2)},20,20,{int(subtitle_style.get('margin_v') or 100)},1"
    )
    styles.append(subtitle_style_line)
    for start_time, end_time, text in subtitle_events:
        events.append(
            f"Dialogue: 0,{_ass_ts(start_time)},{_ass_ts(end_time)},Subtitle,,0,0,0,,{_escape_ass(text)}"
        )

    return "\n".join(
        [
            "[Script Info]",
            "ScriptType: v4.00+",
            "WrapStyle: 0",
            "ScaledBorderAndShadow: yes",
            "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
            *styles,
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
            *events,
        ]
    )


def _write_text_segment(
    *,
    output_path: Path,
    width: int,
    height: int,
    duration_sec: float,
    background_color: str,
    text: str,
    audio_path: Path,
    audio_volume: float,
) -> None:
    ass_path = output_path.with_suffix(".ass")
    ass_path.write_text(
        _build_overlay_ass(
            duration_sec=duration_sec,
            width=width,
            height=height,
            top_safe=height // 4,
            bottom_safe=height // 4,
            padding_x=40,
            slot_config={
                "title": {
                    "enabled": True,
                    "text": text,
                    "font_family": "Noto Sans CJK KR",
                    "font_size": 64,
                    "font_weight": "700",
                    "color": "#FFFFFF",
                    "stroke_color": "#000000",
                    "stroke_width": 3,
                    "background_color": "#000000",
                    "padding": 12,
                    "align": "center",
                    "max_width": width - 120,
                    "line_clamp": 3,
                    "anchor": "center",
                    "offset_x": 0,
                    "offset_y": 0,
                }
            },
            subtitle_events=[],
            subtitle_style={},
        ),
        encoding="utf-8",
    )
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c={background_color}:s={width}x{height}:d={duration_sec}",
        "-i",
        str(audio_path),
        "-vf",
        f"ass={ass_path.name}",
        "-r",
        "30",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "24",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-ar",
        "44100",
        "-ac",
        "2",
        "-af",
        f"volume={audio_volume}",
        "-shortest",
        output_path.name,
    ]
    _run(cmd, cwd=output_path.parent)


def _render_main_segment(
    db: Session,
    *,
    source_path: Path,
    episode_id: str,
    candidate: Candidate,
    span: dict[str, Any],
    output_path: Path,
    width: int,
    height: int,
    config: dict[str, Any],
    subtitle_events_override: list[tuple[float, float, str]] | None = None,
    subtitle_external_file: Path | None = None,
    subtitle_external_is_vtt: bool = False,
) -> tuple[list[tuple[float, float, str]], dict[str, Any]]:
    duration_sec = float(span["end_time"]) - float(span["start_time"])
    top_safe = int(config.get("top_safe_area_height") or 240)
    bottom_safe = int(config.get("bottom_safe_area_height") or 300)
    padding_x = int(config.get("content_padding_x") or 28)
    padding_y = int(config.get("content_padding_y") or 18)
    content_width = max(320, width - padding_x * 2)
    content_height = max(320, height - top_safe - bottom_safe - padding_y * 2)
    background_color = str(config.get("background_color") or "#111111")
    content_bg_color = str(config.get("content_background_color") or "#000000")
    fit_mode = str(config.get("fit_mode") or "contain")
    subtitle_source = str(config.get("subtitle_source") or "transcript")
    subtitle_events = subtitle_events_override or []
    if config.get("burned_caption", True) and subtitle_source != "none" and subtitle_events_override is None:
        subtitle_events = _build_transcript_events(
            db,
            episode_id=episode_id,
            clip_start=float(span["start_time"]),
            clip_end=float(span["end_time"]),
        )
    overlay_ass_path = output_path.with_suffix(".ass")
    overlay_ass_path.write_text(
        _build_overlay_ass(
            duration_sec=duration_sec,
            width=width,
            height=height,
            top_safe=top_safe,
            bottom_safe=bottom_safe,
            padding_x=padding_x,
            slot_config=config.get("text_slots") or {},
            subtitle_events=subtitle_events if subtitle_source == "transcript" else [],
            subtitle_style=config.get("subtitle_style") or {},
        ),
        encoding="utf-8",
    )

    external_subtitle_filter = ""
    if subtitle_external_file is not None and subtitle_external_file.is_file():
        external_subtitle_filter = (
            f",subtitles={_ffmpeg_filter_path(subtitle_external_file)}:charenc=UTF-8"
            if subtitle_external_is_vtt
            else f",subtitles={_ffmpeg_filter_path(subtitle_external_file)}"
        )

    if fit_mode == "cover":
        fit_filter = (
            f"[0:v]scale={content_width}:{content_height}:force_original_aspect_ratio=increase,"
            f"crop={content_width}:{content_height}{external_subtitle_filter}[content]"
        )
    elif fit_mode == "pad-blur":
        fit_filter = (
            "[0:v]split=2[bgsrc][fgsrc];"
            f"[bgsrc]scale={content_width}:{content_height}:force_original_aspect_ratio=increase,"
            f"crop={content_width}:{content_height},boxblur=20:10{external_subtitle_filter}[bgcontent];"
            f"[fgsrc]scale={content_width}:{content_height}:force_original_aspect_ratio=decrease[fgcontent];"
            "[bgcontent][fgcontent]overlay=(W-w)/2:(H-h)/2[content]"
        )
    else:
        fit_filter = (
            f"[0:v]scale={content_width}:{content_height}:force_original_aspect_ratio=decrease,"
            f"pad={content_width}:{content_height}:(ow-iw)/2:(oh-ih)/2:color={content_bg_color}"
            f"{external_subtitle_filter}[content]"
        )
    original_audio_volume = 0.7 if config.get("duck_original_audio") else 1.0
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        str(span["start_time"]),
        "-i",
        str(source_path),
        "-t",
        str(duration_sec),
        "-filter_complex",
        (
            f"color=c={background_color}:s={width}x{height}:d={duration_sec}[canvas];"
            f"{fit_filter};"
            f"[canvas][content]overlay={padding_x}:{top_safe + padding_y}[composed];"
            f"[composed]ass={overlay_ass_path.name},format=yuv420p[outv]"
        ),
        "-map",
        "[outv]",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-r",
        "30",
        "-preset",
        "veryfast",
        "-crf",
        "22",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-ar",
        "44100",
        "-ac",
        "2",
        "-af",
        f"volume={original_audio_volume}",
        "-movflags",
        "+faststart",
        output_path.name,
    ]
    _run(cmd, cwd=output_path.parent)
    return subtitle_events, {
        "span": span,
        "path": str(output_path.resolve()),
        "duration_sec": round(duration_sec, 3),
            "subtitle_source": subtitle_source,
    }


def render_video_draft_assets(
    db: Session,
    *,
    video_draft: VideoDraft,
    render_revision: int,
    output_dir: Path,
    target_stem: str,
) -> dict[str, Any]:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg가 필요합니다.")

    candidate = db.get(Candidate, video_draft.candidate_id)
    script_draft = db.get(ScriptDraft, video_draft.script_draft_id)
    if candidate is None or script_draft is None:
        raise ValueError("Candidate or ScriptDraft not found")
    episode = db.get(Episode, candidate.episode_id)
    if episode is None:
        raise ValueError("Episode not found")

    output_dir.mkdir(parents=True, exist_ok=True)
    source_path = Path(episode.source_video_path).expanduser()
    if not source_path.is_absolute():
        source_path = (get_settings().resolved_storage_root / source_path).resolve()
    else:
        source_path = source_path.resolve()
    if not source_path.is_file():
        raise FileNotFoundError(f"source video missing: {source_path}")

    default_config = build_default_video_render_config(
        episode=episode,
        candidate=candidate,
        script_draft=script_draft,
        template_type=video_draft.template_type,
        burned_caption=video_draft.burned_caption,
        tts_voice_key=video_draft.tts_voice_key,
    )
    existing_config = video_draft.render_config_json or {}
    config = _deep_merge(default_config, existing_config)
    config["burned_caption"] = bool(video_draft.burned_caption)
    width = int(config.get("width") or video_draft.width or 1080)
    height = int(config.get("height") or video_draft.height or 1920)
    video_draft.width = width
    video_draft.height = height
    video_draft.aspect_ratio = str(config.get("aspect_ratio") or video_draft.aspect_ratio or "9:16")
    video_draft.template_type = str(config.get("template_type") or video_draft.template_type)
    video_draft.tts_voice_key = str(config.get("tts_voice_key") or video_draft.tts_voice_key or "ko_female_01")

    segment_files: list[Path] = []
    timeline_segments: list[dict[str, Any]] = []
    all_subtitle_events: list[tuple[float, float, str]] = []
    cursor = 0.0

    def append_text_segment(kind: str, enabled_key: str, text_key: str, duration_key: str) -> dict[str, Any] | None:
        nonlocal cursor
        if not config.get(enabled_key):
            return None
        text = str(config.get(text_key) or "").strip()
        duration_sec = float(config.get(duration_key) or 0.0)
        if duration_sec <= 0:
            return None
        audio_result = synthesize_short_tts(
            text=text,
            output_path=output_dir / f"{kind}_tts_r{render_revision}.mp3",
            voice_key=str(config.get("tts_voice_key") or video_draft.tts_voice_key),
            duration_sec=duration_sec,
        )
        final_segment_duration = float(audio_result["final_segment_duration_sec"])
        segment_path = output_dir / f"{kind}_segment_r{render_revision}.mp4"
        _write_text_segment(
            output_path=segment_path,
            width=width,
            height=height,
            duration_sec=final_segment_duration,
            background_color=str(config.get("background_color") or "#111111"),
            text=text,
            audio_path=Path(audio_result["path"]),
            audio_volume=float(config.get("tts_volume") or 1.0),
        )
        segment_files.append(segment_path)
        entry = {
            "kind": kind,
            "path": str(segment_path.resolve()),
            "start_time": round(cursor, 3),
            "end_time": round(cursor + final_segment_duration, 3),
            "tts": audio_result,
        }
        cursor += final_segment_duration
        timeline_segments.append(entry)
        return entry

    append_text_segment("intro", "intro_tts_enabled", "intro_tts_text", "intro_duration_sec")

    spans = candidate_clip_spans(candidate)
    candidate_dir = episode_root(candidate.episode_id) / "candidates" / candidate.id
    imported_vtt = candidate_dir / IMPORTED_VTT
    imported_ass = candidate_dir / IMPORTED_ASS
    edited_ass = candidate_dir / EDITED_ASS
    subtitle_source = str(config.get("subtitle_source") or "transcript")
    subtitle_mode = subtitle_source
    subtitle_warnings: list[str] = []
    imported_vtt_remapped: list[list[tuple[float, float, str]]] | None = None
    imported_vtt_mode: str | None = None
    if subtitle_source == "file" and imported_vtt.is_file():
        imported_vtt_remapped, imported_vtt_mode = _remap_imported_vtt_events(
            parse_subtitle_upload_file(imported_vtt),
            spans=spans,
            candidate_start=float(candidate.start_time),
        )
    elif subtitle_source == "file" and imported_ass.is_file() and len(spans) > 1:
        subtitle_mode = "transcript"
        subtitle_warnings.append("imported_ass_composite_not_supported_fallback_to_transcript")
    elif subtitle_source == "edited-ass" and len(spans) > 1:
        subtitle_mode = "transcript"
        subtitle_warnings.append("edited_ass_composite_not_supported_fallback_to_transcript")

    for index, span in enumerate(spans, start=1):
        segment_path = output_dir / f"main_span_{index}_r{render_revision}.mp4"
        subtitle_events_override = None
        subtitle_external_file = None
        subtitle_external_is_vtt = False
        if subtitle_mode == "file" and imported_vtt_remapped is not None:
            subtitle_events_override = imported_vtt_remapped[index - 1]
        elif subtitle_mode == "file" and imported_ass.is_file() and len(spans) == 1:
            subtitle_external_file = imported_ass
        elif subtitle_mode == "edited-ass" and edited_ass.is_file() and len(spans) == 1:
            subtitle_external_file = edited_ass
        if subtitle_external_file is not None:
            subtitle_external_is_vtt = subtitle_external_file.suffix.lower() == ".vtt"
        subtitle_events, timeline_meta = _render_main_segment(
            db,
            source_path=source_path,
            episode_id=episode.id,
            candidate=candidate,
            span=span,
            output_path=segment_path,
            width=width,
            height=height,
            config={**config, "subtitle_source": subtitle_mode},
            subtitle_events_override=subtitle_events_override,
            subtitle_external_file=subtitle_external_file,
            subtitle_external_is_vtt=subtitle_external_is_vtt,
        )
        segment_duration = float(timeline_meta["duration_sec"])
        shifted_events = [(start + cursor, end + cursor, text) for start, end, text in subtitle_events]
        all_subtitle_events.extend(shifted_events)
        segment_files.append(segment_path)
        timeline_segments.append(
            {
                "kind": "main",
                **timeline_meta,
                "timeline_start": round(cursor, 3),
                "timeline_end": round(cursor + segment_duration, 3),
            }
        )
        cursor += segment_duration

    append_text_segment("outro", "outro_tts_enabled", "outro_tts_text", "outro_duration_sec")

    concat_file = output_dir / f"{target_stem}_concat_r{render_revision}.txt"
    concat_file.write_text(
        "\n".join(f"file '{segment_file.resolve()}'" for segment_file in segment_files),
        encoding="utf-8",
    )
    final_video_path = output_dir / f"{target_stem}_r{render_revision}.mp4"
    _run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            concat_file.name,
            "-c",
            "copy",
            final_video_path.name,
        ],
        cwd=output_dir,
    )

    subtitle_path: Path | None = None
    if all_subtitle_events:
        subtitle_path = output_dir / f"{target_stem}_r{render_revision}.srt"
        subtitle_path.write_text(_build_srt(all_subtitle_events), encoding="utf-8")

    thumbnail_path = output_dir / f"{target_stem}_thumb_r{render_revision}.jpg"
    _run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            "0.2",
            "-i",
            final_video_path.name,
            "-frames:v",
            "1",
            thumbnail_path.name,
        ],
        cwd=output_dir,
    )

    metadata = {
        "template_type": video_draft.template_type,
        "render_revision": render_revision,
        "provider": "ffmpeg_template_renderer",
        "composite": bool(candidate.metadata_json.get("composite")),
        "clip_spans": spans,
        "subtitle_mode": subtitle_mode,
    }
    if imported_vtt_mode:
        metadata["imported_vtt_remap_mode"] = imported_vtt_mode
    if subtitle_warnings:
        metadata["subtitle_warnings"] = subtitle_warnings
    tts_entries = [segment.get("tts") for segment in timeline_segments if segment.get("tts")]
    if tts_entries:
        metadata["tts_segments"] = tts_entries
    timeline_json = {
        "template_type": video_draft.template_type,
        "segments": timeline_segments,
        "total_duration_sec": round(cursor, 3),
    }
    return {
        "video_path": str(final_video_path.resolve()),
        "subtitle_path": str(subtitle_path.resolve()) if subtitle_path else None,
        "thumbnail_path": str(thumbnail_path.resolve()),
        "render_config": config,
        "timeline_json": timeline_json,
        "metadata": metadata,
    }
