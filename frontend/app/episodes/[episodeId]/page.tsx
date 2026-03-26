import Link from "next/link";
import { notFound } from "next/navigation";
import {
  AnalyzeEpisodeButton,
  ClearEpisodeAnalysisButton,
  ClearEpisodeCacheButton,
  FullReanalyzeEpisodeButton,
  DeleteEpisodeButton
} from "@/components/mutation-buttons";
import { JobsLiveStrip } from "@/components/jobs-live";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { SourceVideoPlayer } from "@/components/source-video-player";
import { TimelineViewer } from "@/components/timeline-viewer";
import { formatDuration, formatEpisodeLabel } from "@/lib/format";
import { ApiHttpError, getEpisode, getEpisodeJobs, getEpisodeTimeline } from "@/lib/api";

export default async function EpisodeDetailPage({
  params
}: {
  params: Promise<{ episodeId: string }>;
}) {
  const { episodeId } = await params;
  const [episode, timeline, jobsResponse] = await Promise.all([
    getEpisode(episodeId),
    getEpisodeTimeline(episodeId),
    getEpisodeJobs(episodeId)
  ]).catch((e: unknown) => {
    if (e instanceof ApiHttpError && e.status === 404) {
      notFound();
    }
    throw e;
  });

  return (
    <main className="page">
      <PageHeader
        title={`${episode.show_title} ${formatEpisodeLabel(episode.season_number, episode.episode_number)}`}
        subtitle={episode.episode_title ?? "에피소드 정보와 분석 진행 상태"}
        backHref="/episodes"
        actions={
          <>
            <AnalyzeEpisodeButton episodeId={episode.id} />
            <FullReanalyzeEpisodeButton episodeId={episode.id} />
            <ClearEpisodeAnalysisButton episodeId={episode.id} />
            <ClearEpisodeCacheButton episodeId={episode.id} />
            <Link href={`/episodes/${episode.id}/candidates`} className="link-button primary">
              후보 목록
            </Link>
            <DeleteEpisodeButton episodeId={episode.id} />
          </>
        }
      />

      <div className="grid three">
        <div className="kpi">
          <span className="muted">상태</span>
          <StatusBadge value={episode.status} />
        </div>
        <div className="kpi">
          <span className="muted">길이</span>
          <strong>{formatDuration(episode.duration_seconds)}</strong>
        </div>
        <div className="kpi">
          <span className="muted">채널</span>
          <strong>{episode.target_channel}</strong>
        </div>
      </div>

      <div className="panel">
        <h2 className="section-title">원본 영상 재생</h2>
        <SourceVideoPlayer episodeId={episode.id} />
        <p className="muted tiny path">원본 경로: {episode.source_video_path}</p>
        <p className="muted tiny">
          프록시: {episode.proxy_video_path ?? "아직 없음"}
          {episode.proxy_video_path ? " (프록시 파일은 별도 경로)" : ""}
        </p>
      </div>

      <JobsLiveStrip initialJobs={jobsResponse.items} episodeId={episodeId} />
      <TimelineViewer timeline={timeline} />
    </main>
  );
}
