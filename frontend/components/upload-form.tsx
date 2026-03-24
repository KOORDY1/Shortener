"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { apiBaseUrl } from "@/lib/api";

export function UploadForm() {
  const router = useRouter();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);

    const form = event.currentTarget;
    const formData = new FormData(form);

    try {
      const response = await fetch(`${apiBaseUrl}/episodes`, {
        method: "POST",
        body: formData
      });
      if (!response.ok) {
        throw new Error("에피소드 업로드에 실패했습니다.");
      }
      const data = (await response.json()) as { id: string };
      router.push(`/episodes/${data.id}`);
      router.refresh();
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "알 수 없는 오류가 발생했습니다.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="panel stack">
      <div className="grid two">
        <div className="field">
          <label htmlFor="show_title">Show Title</label>
          <input id="show_title" name="show_title" className="input" required />
        </div>
        <div className="field">
          <label htmlFor="episode_title">Episode Title</label>
          <input id="episode_title" name="episode_title" className="input" />
        </div>
        <div className="field">
          <label htmlFor="season_number">Season Number</label>
          <input id="season_number" name="season_number" type="number" className="input" />
        </div>
        <div className="field">
          <label htmlFor="episode_number">Episode Number</label>
          <input id="episode_number" name="episode_number" type="number" className="input" />
        </div>
        <div className="field">
          <label htmlFor="original_language">Original Language</label>
          <select id="original_language" name="original_language" className="select" defaultValue="en">
            <option value="en">EN</option>
            <option value="ko">KO</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="target_channel">Target Channel</label>
          <select id="target_channel" name="target_channel" className="select" defaultValue="kr_us_drama">
            <option value="kr_us_drama">KR←US</option>
            <option value="us_kr_drama">US←KR</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="video_file">Video File</label>
          <input id="video_file" name="video_file" type="file" className="input" accept="video/*" required />
        </div>
        <div className="field">
          <label htmlFor="subtitle_file">Subtitle File</label>
          <input id="subtitle_file" name="subtitle_file" type="file" className="input" accept=".srt,.vtt,text/plain" />
        </div>
      </div>
      {error ? <div className="badge failed">{error}</div> : null}
      <div className="row">
        <button type="submit" className="button primary" disabled={submitting}>
          {submitting ? "Uploading..." : "Upload & Save"}
        </button>
      </div>
    </form>
  );
}
