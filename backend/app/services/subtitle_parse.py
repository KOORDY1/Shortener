"""업로드된 SRT / WebVTT에서 구간 자막을 읽어 DB용 큐로 변환합니다."""

from __future__ import annotations

import re
from pathlib import Path

_TS_ARROW = re.compile(r"^(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,.]\d{3})")


def _timestamp_to_seconds(ts: str) -> float:
    ts = ts.strip().replace(",", ".")
    h, m, s = ts.split(":", 2)
    return int(h) * 3600 + int(m) * 60 + float(s)


def _parse_cue_block_lines(lines: list[str]) -> tuple[float, float, str] | None:
    for j, line in enumerate(lines):
        m = _TS_ARROW.match(line.strip())
        if not m:
            continue
        start = _timestamp_to_seconds(m.group(1))
        end = _timestamp_to_seconds(m.group(2))
        text = "\n".join(lines[j + 1 :]).strip()
        return (start, end, text or " ")
    return None


def _parse_cue_blocks(body: str) -> list[tuple[float, float, str]]:
    body = body.replace("\r\n", "\n").strip()
    if not body:
        return []
    cues: list[tuple[float, float, str]] = []
    for block in re.split(r"\n\n+", body):
        lines = [ln for ln in block.split("\n") if ln.strip()]
        if not lines:
            continue
        if lines[0].strip().isdigit():
            lines = lines[1:]
        parsed = _parse_cue_block_lines(lines)
        if parsed:
            cues.append(parsed)
    return cues


def parse_subtitle_upload_file(path: Path) -> list[tuple[float, float, str]]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    if raw.startswith("\ufeff"):
        raw = raw[1:]
    stripped = raw.lstrip()
    if path.suffix.lower() == ".vtt" or stripped.upper().startswith("WEBVTT"):
        # 헤더·NOTE 등 건너뛰고 첫 큐부터
        idx = raw.find("\n\n")
        if idx == -1:
            return []
        return _parse_cue_blocks(raw[idx + 2 :])
    return _parse_cue_blocks(raw)
