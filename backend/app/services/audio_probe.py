from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


def probe_audio_duration_seconds(audio_path: Path) -> float | None:
    path = audio_path.expanduser().resolve()
    if not path.is_file():
        return None
    if shutil.which("ffprobe") is None:
        return None
    try:
        completed = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_format",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        payload = json.loads(completed.stdout or "{}")
        duration = payload.get("format", {}).get("duration")
        if duration in (None, "", "N/A"):
            return None
        value = float(duration)
        return round(value, 3) if value > 0 else None
    except Exception:
        return None
