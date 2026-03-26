import Link from "next/link";
import { notFound } from "next/navigation";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { getExport, getVideoDraft } from "@/lib/api";

export default async function ExportDetailPage({
  params
}: {
  params: Promise<{ exportId: string }>;
}) {
  const { exportId } = await params;
  const exp = await getExport(exportId).catch(() => notFound());
  const draft = await getVideoDraft(exp.video_draft_id).catch(() => notFound());

  return (
    <main className="page">
      <PageHeader
        title="보내기 결과"
        subtitle={exp.export_preset}
        backHref={`/drafts/${exp.video_draft_id}`}
      />

      <div className="grid two">
        <div className="panel stack">
          <div className="spaced">
            <span className="muted">상태</span>
            <StatusBadge value={exp.status} />
          </div>
          <div>
            <span className="muted">비디오 초안</span>
            <p>
              <Link href={`/drafts/${exp.video_draft_id}`} className="link-button">
                v{draft.version_no} 열기
              </Link>
            </p>
          </div>
          {exp.file_size_bytes != null ? (
            <div>
              <span className="muted">크기(bytes)</span>
              <p>{exp.file_size_bytes}</p>
            </div>
          ) : null}
        </div>

        <div className="panel stack">
          <h2 className="section-title">파일 경로</h2>
          {exp.export_video_path ? (
            <div>
              <span className="muted">영상</span>
              <p className="tiny path">{exp.export_video_path}</p>
            </div>
          ) : null}
          {exp.export_subtitle_path ? (
            <div>
              <span className="muted">자막</span>
              <p className="tiny path">{exp.export_subtitle_path}</p>
            </div>
          ) : null}
          {exp.export_script_path ? (
            <div>
              <span className="muted">스크립트</span>
              <p className="tiny path">{exp.export_script_path}</p>
            </div>
          ) : null}
          {exp.export_metadata_path ? (
            <div>
              <span className="muted">메타데이터</span>
              <p className="tiny path">{exp.export_metadata_path}</p>
            </div>
          ) : null}
        </div>
      </div>
    </main>
  );
}
