from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Candidate, Episode
from app.services.storage_service import episode_root
from app.services.subtitle_exchange import (
    GENERATED_ASS,
    build_ass_for_clip,
    edited_ass_path,
    find_imported_subtitle_file,
    transcript_segments_for_clip,
)


QUALITY_PRESETS: dict[str, dict[str, str]] = {
    "draft": {"preset": "veryfast", "crf": "30", "audio_bitrate": "96k"},
    "standard": {"preset": "fast", "crf": "23", "audio_bitrate": "128k"},
    "high": {"preset": "medium", "crf": "20", "audio_bitrate": "160k"},
}


def _output_filename(output_kind: str) -> str:
    return "preview_clip.mp4" if output_kind == "preview" else "short_clip.mp4"


def _preview_dimensions(width: int, height: int) -> tuple[int, int]:
    longest = max(width, height)
    if longest <= 960:
        return width, height
    scale = 960 / float(longest)
    scaled_w = max(2, int(round(width * scale / 2)) * 2)
    scaled_h = max(2, int(round(height * scale / 2)) * 2)
    return scaled_w, scaled_h


def _subtitle_filter(filename: str, *, is_vtt: bool) -> str:
    if is_vtt:
        return f"subtitles={filename}:charenc=UTF-8"
    return f"subtitles={filename}"


def _build_video_filter(
    *,
    width: int,
    height: int,
    fit_mode: str,
    subtitle_filename: str | None,
    subtitle_is_vtt: bool = False,
) -> str:
    if fit_mode == "cover":
        base = (
            f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height}[composed]"
        )
    elif fit_mode == "pad-blur":
        base = (
            "[0:v]split=2[bgsrc][fgsrc];"
            f"[bgsrc]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},boxblur=20:10[bg];"
            f"[fgsrc]scale={width}:{height}:force_original_aspect_ratio=decrease[fg];"
            "[bg][fg]overlay=(W-w)/2:(H-h)/2[composed]"
        )
    else:
        base = (
            f"[0:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2[composed]"
        )

    if subtitle_filename is None:
        return f"{base};[composed]format=yuv420p[outv]"
    subtitle = _subtitle_filter(subtitle_filename, is_vtt=subtitle_is_vtt)
    return f"{base};[composed]{subtitle},format=yuv420p[outv]"


def render_candidate_short_clip(
    db: Session,
    *,
    candidate: Candidate,
    trim_start: float,
    trim_end: float,
    burn_subtitles: bool,
    width: int,
    height: int,
    fit_mode: str = "contain",
    quality_preset: str = "standard",
    subtitle_style: dict[str, Any] | None = None,
    subtitle_text_overrides: dict[str, str] | None = None,
    use_imported_subtitles: bool = False,
    use_edited_ass: bool = False,
    output_kind: str = "final",
) -> str:
    if not shutil.which("ffmpeg"):
        raise RuntimeError(
            "ffmpeg가 PATH에 없습니다. Docker 이미지에 ffmpeg를 설치했는지 확인하세요."
        )

    if trim_end <= trim_start:
        raise ValueError("끝 시각이 시작 시각보다 커야 합니다.")

    episode = db.get(Episode, candidate.episode_id)
    if episode is None:
        raise ValueError("에피소드를 찾을 수 없습니다.")

    settings = get_settings()
    src = Path(episode.source_video_path).expanduser()
    if not src.is_absolute():
        src = (settings.resolved_storage_root / src).resolve()
    else:
        src = src.resolve()
    if not src.is_file():
        raise FileNotFoundError(f"원본 영상이 없습니다: {src}")

    if quality_preset not in QUALITY_PRESETS:
        raise ValueError("지원하지 않는 quality_preset 입니다.")
    if fit_mode not in {"cover", "contain", "pad-blur"}:
        raise ValueError("지원하지 않는 fit_mode 입니다.")

    duration = trim_end - trim_start
    render_width, render_height = (
        _preview_dimensions(width, height) if output_kind == "preview" else (width, height)
    )
    out_dir = episode_root(candidate.episode_id) / "candidates" / candidate.id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_mp4 = out_dir / _output_filename(output_kind)
    ass_path = out_dir / GENERATED_ASS

    imported: Path | None = None
    subtitle_file: Path | None = None
    subtitle_is_vtt = False
    has_subs = False
    if burn_subtitles:
        if use_imported_subtitles:
            imported = find_imported_subtitle_file(out_dir)
            if imported is None:
                raise ValueError(
                    "가져온 자막이 없습니다. API로 .ass 또는 .vtt를 업로드한 뒤 다시 시도하세요."
                )
            has_subs = True
            subtitle_file = imported
            subtitle_is_vtt = imported.suffix.lower() == ".vtt"
        elif use_edited_ass:
            candidate_ass = edited_ass_path(candidate.episode_id, candidate.id)
            if not candidate_ass.is_file():
                raise ValueError("저장된 ASS 원문이 없습니다. 먼저 ASS 원문을 저장하세요.")
            has_subs = True
            subtitle_file = candidate_ass
        else:
            segs = transcript_segments_for_clip(db, candidate.episode_id, trim_start, trim_end)
            ass_body = build_ass_for_clip(
                segs,
                trim_start,
                trim_end,
                style=subtitle_style,
                text_overrides=subtitle_text_overrides,
            )
            has_subs = "[Events]" in ass_body and "Dialogue:" in ass_body
            ass_path.write_text(ass_body, encoding="utf-8")
            subtitle_file = ass_path

    video_filter = _build_video_filter(
        width=render_width,
        height=render_height,
        fit_mode=fit_mode,
        subtitle_filename=subtitle_file.name
        if burn_subtitles and has_subs and subtitle_file
        else None,
        subtitle_is_vtt=subtitle_is_vtt,
    )
    quality = QUALITY_PRESETS[quality_preset]

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        str(trim_start),
        "-i",
        str(src),
        "-t",
        str(duration),
        "-filter_complex",
        video_filter,
        "-map",
        "[outv]",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-preset",
        quality["preset"],
        "-crf",
        quality["crf"],
        "-c:a",
        "aac",
        "-b:a",
        quality["audio_bitrate"],
        "-movflags",
        "+faststart",
        out_mp4.name,
    ]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=3600,
        cwd=str(out_dir),
        check=False,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"ffmpeg 실패 (exit {proc.returncode}): {err[-4000:]}")

    return str(out_mp4.resolve())
