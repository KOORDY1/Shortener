import { notFound } from "next/navigation";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { VideoDraftActions } from "@/components/video-draft-actions";
import { getVideoDraft } from "@/lib/api";

export default async function VideoDraftPage({
  params
}: {
  params: Promise<{ draftId: string }>;
}) {
  const { draftId } = await params;
  const draft = await getVideoDraft(draftId).catch(() => notFound());

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
          {draft.draft_video_path ? (
            <div>
              <span className="muted">초안 영상 경로</span>
              <p className="tiny path">{draft.draft_video_path}</p>
            </div>
          ) : null}
          {draft.tts_voice_key ? (
            <div>
              <span className="muted">TTS</span>
              <p>{draft.tts_voice_key}</p>
            </div>
          ) : null}
        </div>

        <div className="panel">
          <h2 className="section-title">편집 · 보내기</h2>
          <VideoDraftActions draft={draft} />
        </div>
      </div>
    </main>
  );
}
