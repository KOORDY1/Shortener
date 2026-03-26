"use client";

import { useQuery } from "@tanstack/react-query";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { DebugDisclosure } from "@/components/debug-disclosure";
import { VideoDraftActions } from "@/components/video-draft-actions";
import { VideoDraftTemplateEditor } from "@/components/video-draft-template-editor";
import { apiBaseUrl } from "@/lib/api";
import { fetchJobsForCandidate, fetchVideoDraft } from "@/lib/public-api";
import type { Job, TtsSegmentMetadata, VideoDraftDetail } from "@/lib/types";

type Props = {
  initialDraft: VideoDraftDetail;
};

function hasActiveDraftJobs(jobs: Job[]) {
  return jobs.some(
    (job) =>
      (job.type === "video_draft_render" || job.type === "export_render") &&
      (job.status === "queued" || job.status === "running")
  );
}

export function VideoDraftLiveView({ initialDraft }: Props) {
  const { data: jobs = [] } = useQuery({
    queryKey: ["jobs", "candidate", initialDraft.candidate_id, "draft-page"],
    queryFn: () => fetchJobsForCandidate(initialDraft.candidate_id),
    refetchInterval: 2000
  });
  const { data: draft = initialDraft } = useQuery({
    queryKey: ["videoDraft", initialDraft.id],
    queryFn: () => fetchVideoDraft(initialDraft.id),
    initialData: initialDraft,
    refetchInterval: hasActiveDraftJobs(jobs) ? 2000 : false
  });
  const ttsSegments = Array.isArray(draft.metadata.tts_segments)
    ? (draft.metadata.tts_segments as TtsSegmentMetadata[])
    : [];
  const hasSilentFallback = ttsSegments.some((segment) => segment.provider === "silent_fallback");

  return (
    <main className="page">
      <PageHeader
        title={`비디오 초안 v${draft.version_no}`}
        subtitle={`${draft.template_type} · 화면비 ${draft.aspect_ratio}`}
        backHref={`/candidates/${draft.candidate_id}`}
      />

      <div className="grid two">
        <div className="panel stack">
          <div className="spaced">
            <span className="muted">상태</span>
            <StatusBadge value={draft.status} />
          </div>
          <div>
            <span className="muted">스크립트 초안</span>
            <p className="tiny path">{draft.script_draft_id}</p>
          </div>
          <div>
            <span className="muted">해상도</span>
            <p>
              {draft.width}×{draft.height}
            </p>
          </div>
          <div>
            <span className="muted">자막 번인</span>
            <p>{draft.burned_caption ? "예" : "아니오"}</p>
          </div>
          {draft.tts_voice_key ? (
            <div>
              <span className="muted">TTS</span>
              <p>{draft.tts_voice_key}</p>
            </div>
          ) : null}
          {ttsSegments.length > 0 ? (
            <div className="stack">
              <span className="muted">TTS 세그먼트</span>
              {ttsSegments.map((segment, index) => (
                <div key={`${segment.provider}-${index}`} className="panel soft">
                  <div className="row wrap">
                    <StatusBadge value={segment.provider === "silent_fallback" ? "failed" : "ready"} />
                    <span className="muted tiny">{segment.provider}</span>
                  </div>
                  <div className="muted tiny">
                    요청 {segment.requested_duration_sec}s / 실제 오디오 {segment.actual_audio_duration_sec}s / 최종 세그먼트{" "}
                    {segment.final_segment_duration_sec}s
                  </div>
                  {segment.fallback_reason ? (
                    <div className="muted tiny" style={{ color: "var(--danger, #c00)" }}>
                      fallback: {segment.fallback_reason}
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
          ) : null}
        </div>

        <div className="panel stack">
          <div className="spaced">
            <h2 className="section-title">미리보기</h2>
            {hasActiveDraftJobs(jobs) ? <StatusBadge value="running" /> : null}
          </div>
          {hasSilentFallback ? (
            <p className="muted" style={{ color: "var(--danger, #c00)" }}>
              일부 TTS 세그먼트가 `silent_fallback`으로 렌더되었습니다. 음성이 비어 있을 수 있습니다.
            </p>
          ) : null}
          {draft.draft_video_path ? (
            <video
              key={draft.draft_video_path}
              className="source-video"
              controls
              preload="metadata"
              src={`${apiBaseUrl}/video-drafts/${draft.id}/video?v=${encodeURIComponent(
                draft.draft_video_path
              )}`}
            />
          ) : (
            <p className="muted">아직 렌더된 비디오가 없습니다.</p>
          )}
        </div>
      </div>

      <DebugDisclosure title="디버그 정보 보기">
        {draft.draft_video_path ? (
          <div>
            <strong>draft_video_path</strong>
            <p className="tiny path">{draft.draft_video_path}</p>
          </div>
        ) : null}
        {draft.subtitle_path ? (
          <div>
            <strong>subtitle_path</strong>
            <p className="tiny path">{draft.subtitle_path}</p>
          </div>
        ) : null}
        {draft.thumbnail_path ? (
          <div>
            <strong>thumbnail_path</strong>
            <p className="tiny path">{draft.thumbnail_path}</p>
          </div>
        ) : null}
        <div>
          <strong>metadata</strong>
          <pre className="tiny path">{JSON.stringify(draft.metadata, null, 2)}</pre>
        </div>
        <div>
          <strong>render_config</strong>
          <pre className="tiny path">{JSON.stringify(draft.render_config, null, 2)}</pre>
        </div>
      </DebugDisclosure>

      <div className="grid two">
        <VideoDraftTemplateEditor draft={draft} />
        <div className="panel">
          <h2 className="section-title">편집 · 보내기</h2>
          <VideoDraftActions draft={draft} />
        </div>
      </div>
    </main>
  );
}
