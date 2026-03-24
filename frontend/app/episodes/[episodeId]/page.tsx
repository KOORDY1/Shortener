import Link from "next/link";
import { notFound } from "next/navigation";
import { AnalyzeEpisodeButton } from "@/components/mutation-buttons";
import { JobsLiveStrip } from "@/components/jobs-live";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { TimelineViewer } from "@/components/timeline-viewer";
import { formatDuration, formatEpisodeLabel } from "@/lib/format";
import { getEpisode, getEpisodeJobs, getEpisodeTimeline } from "@/lib/api";

export default async function EpisodeDetailPage({
  params
}: {
  params: Promise<{ episodeId: string }>;
}) {
  const { episodeId } = await params;

  try {
    const [episode, timeline, jobsResponse] = await Promise.all([
      getEpisode(episodeId),
      getEpisodeTimeline(episodeId),
      getEpisodeJobs(episodeId)
    ]);

    return (
      <main className="page">
        <PageHeader
          title={`${episode.show_title} ${formatEpisodeLabel(episode.season_number, episode.episode_number)}`}
          subtitle={episode.episode_title ?? "에피소드 메타와 분석 진행 상태"}
          backHref="/episodes"
          actions={
            <>
              <AnalyzeEpisodeButton episodeId={episode.id} />
              <Link href={`/episodes/${episode.id}/candidates`} className="link-button primary">
                Candidates
              </Link>
            </>
          }
        />

        <div className="grid three">
          <div className="kpi">
            <span className="muted">Status</span>
            <StatusBadge value={episode.status} />
          </div>
          <div className="kpi">
            <span className="muted">Duration</span>
            <strong>{formatDuration(episode.duration_seconds)}</strong>
          </div>
          <div className="kpi">
            <span className="muted">Target</span>
            <strong>{episode.target_channel}</strong>
          </div>
        </div>

        <div className="panel">
          <h2 className="section-title">Preview</h2>
          <div className="thumbnail">{episode.proxy_video_path ? "Proxy Ready" : "Proxy pending"}</div>
          <p className="muted">Source: {episode.source_video_path}</p>
          <p className="muted">Proxy: {episode.proxy_video_path ?? "not generated yet"}</p>
        </div>

        <JobsLiveStrip initialJobs={jobsResponse.items} episodeId={episodeId} />
        <TimelineViewer timeline={timeline} />
      </main>
    );
  } catch {
    notFound();
  }
}
