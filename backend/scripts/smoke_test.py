from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
SMOKE_DATA_DIR = BASE_DIR / "data" / "smoke"
SMOKE_STORAGE_DIR = BASE_DIR / "storage" / "smoke"


def prepare_smoke_env() -> None:
    if SMOKE_DATA_DIR.exists():
        shutil.rmtree(SMOKE_DATA_DIR)
    if SMOKE_STORAGE_DIR.exists():
        shutil.rmtree(SMOKE_STORAGE_DIR)

    SMOKE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    SMOKE_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

    os.environ["DATABASE_URL"] = f"sqlite:///{(SMOKE_DATA_DIR / 'smoke.db').as_posix()}"
    os.environ["STORAGE_ROOT"] = str(SMOKE_STORAGE_DIR)
    os.environ["CELERY_BROKER_URL"] = "memory://"
    os.environ["CELERY_RESULT_BACKEND"] = "cache+memory://"
    os.environ["CELERY_TASK_ALWAYS_EAGER"] = "true"
    os.environ["ALLOW_MOCK_LLM_FALLBACK"] = "true"


def build_smoke_video_bytes() -> bytes:
    output_path = SMOKE_DATA_DIR / "sample.mp4"
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "color=c=#202020:s=1280x720:d=18",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:sample_rate=44100:d=18",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        str(output_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return output_path.read_bytes()


def run() -> None:
    prepare_smoke_env()
    video_bytes = build_smoke_video_bytes()

    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app()
    with TestClient(app) as client:
        create_response = client.post(
            "/api/v1/episodes",
            data={
                "show_title": "Silicon Valley",
                "season_number": "1",
                "episode_number": "3",
                "episode_title": "Articles of Incorporation",
                "original_language": "en",
                "target_channel": "kr_us_drama",
            },
            files={"video_file": ("episode.mp4", video_bytes, "video/mp4")},
        )
        create_response.raise_for_status()
        episode = create_response.json()
        episode_id = episode["id"]

        analyze_response = client.post(
            f"/api/v1/episodes/{episode_id}/analyze",
            json={"force_reanalyze": False},
        )
        analyze_response.raise_for_status()
        analyze_job = analyze_response.json()

        job_response = client.get(f"/api/v1/jobs/{analyze_job['job_id']}")
        job_response.raise_for_status()
        job_payload = job_response.json()
        assert job_payload["status"] == "succeeded", job_payload

        episode_jobs = client.get(f"/api/v1/episodes/{episode_id}/jobs")
        episode_jobs.raise_for_status()
        assert episode_jobs.json()["total"] >= 1

        candidates_response = client.get(f"/api/v1/episodes/{episode_id}/candidates")
        candidates_response.raise_for_status()
        candidates = candidates_response.json()["items"]
        assert candidates, "Expected candidates to be generated"
        candidate_id = candidates[0]["id"]

        detail = client.get(f"/api/v1/candidates/{candidate_id}")
        detail.raise_for_status()
        assert "shots" in detail.json() and isinstance(detail.json()["shots"], list)

        drafts_response = client.post(
            f"/api/v1/candidates/{candidate_id}/script-drafts",
            json={
                "language": "ko",
                "versions": 2,
                "tone": "sharp_explanatory",
                "channel_style": "kr_us_drama",
                "force_regenerate": True,
            },
        )
        drafts_response.raise_for_status()
        draft_job = drafts_response.json()

        draft_job_response = client.get(f"/api/v1/jobs/{draft_job['job_id']}")
        draft_job_response.raise_for_status()
        draft_job_payload = draft_job_response.json()
        assert draft_job_payload["status"] == "succeeded", draft_job_payload

        final_drafts_response = client.get(f"/api/v1/candidates/{candidate_id}/script-drafts")
        final_drafts_response.raise_for_status()
        script_drafts = final_drafts_response.json()["items"]
        assert len(script_drafts) == 2, script_drafts
        script_draft_id = script_drafts[0]["id"]

        vd_create = client.post(
            f"/api/v1/candidates/{candidate_id}/video-drafts",
            json={"script_draft_id": script_draft_id},
        )
        vd_create.raise_for_status()
        video_draft_id = vd_create.json()["video_draft_id"]
        assert video_draft_id

        vd_get = client.get(f"/api/v1/video-drafts/{video_draft_id}")
        vd_get.raise_for_status()
        assert vd_get.json()["status"] == "ready"

        rerender = client.post(f"/api/v1/video-drafts/{video_draft_id}/rerender", json={})
        rerender.raise_for_status()
        rerender_payload = rerender.json()
        assert rerender_payload.get("job_id")

        approve = client.post(f"/api/v1/video-drafts/{video_draft_id}/approve", json={})
        approve.raise_for_status()
        assert approve.json()["status"] == "approved"

        export_resp = client.post(
            f"/api/v1/video-drafts/{video_draft_id}/exports",
            json={
                "export_preset": "shorts_default",
                "include_srt": True,
                "include_script_txt": True,
                "include_metadata_json": True,
            },
        )
        export_resp.raise_for_status()
        export_id = export_resp.json()["export_id"]
        assert export_id

        export_get = client.get(f"/api/v1/exports/{export_id}")
        export_get.raise_for_status()
        export_body = export_get.json()
        assert export_body["status"] == "ready"
        assert export_body.get("export_video_path")

        print(
            json.dumps(
                {
                    "episode_id": episode_id,
                    "analysis_job_id": analyze_job["job_id"],
                    "candidate_id": candidate_id,
                    "script_job_id": draft_job["job_id"],
                    "script_draft_ids": [item["id"] for item in script_drafts],
                    "video_draft_id": video_draft_id,
                    "rerender_job_id": rerender_payload["job_id"],
                    "export_id": export_id,
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    run()
