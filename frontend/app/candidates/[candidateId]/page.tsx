import Link from "next/link";
import { notFound } from "next/navigation";
import { CandidateJobsAndDraftsLive } from "@/components/candidate-jobs-and-drafts-live";
import { CandidateGenerateScriptsButton } from "@/components/mutation-buttons";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { formatDuration, formatTimecode } from "@/lib/format";
import { getCandidate, getCandidateScriptDrafts, getJobs } from "@/lib/api";

export default async function CandidateDetailPage({
  params
}: {
  params: Promise<{ candidateId: string }>;
}) {
  const { candidateId } = await params;

  try {
    const [candidate, drafts, jobs] = await Promise.all([
      getCandidate(candidateId),
      getCandidateScriptDrafts(candidateId),
      getJobs({ candidate_id: candidateId })
    ]);

    return (
      <main className="page">
        <PageHeader
          title={`Candidate #${candidateId.slice(0, 8)}`}
          subtitle={candidate.title_hint}
          backHref={`/episodes/${candidate.episode_id}/candidates`}
          actions={
            <>
              <CandidateGenerateScriptsButton candidateId={candidateId} />
              <Link href={`/episodes/${candidate.episode_id}`} className="link-button">
                Episode
              </Link>
            </>
          }
        />

        <div className="grid three">
          <div className="kpi">
            <span className="muted">Time</span>
            <strong>
              {formatTimecode(candidate.start_time)} - {formatTimecode(candidate.end_time)}
            </strong>
          </div>
          <div className="kpi">
            <span className="muted">Duration</span>
            <strong>{formatDuration(candidate.duration_seconds)}</strong>
          </div>
          <div className="kpi">
            <span className="muted">Score / Risk</span>
            <strong>
              {candidate.scores.total_score ?? "-"} / {candidate.risk.risk_score}
            </strong>
          </div>
        </div>

        <div className="panel">
          <div className="row">
            <StatusBadge value={candidate.status} />
            <StatusBadge value={candidate.type} />
            <StatusBadge value={candidate.risk.risk_level} />
          </div>
          <p className="muted">Reasons: {candidate.risk.reasons.join(", ") || "none"}</p>
        </div>

        <div className="panel">
          <h2 className="section-title">Scores</h2>
          <div className="grid three">
            {Object.entries(candidate.scores).map(([key, value]) => (
              <div key={key} className="kpi">
                <span className="muted">{key}</span>
                <strong>{value}</strong>
              </div>
            ))}
          </div>
        </div>

        <div className="panel">
          <h2 className="section-title">Shots in range</h2>
          <div className="shot-strip">
            {candidate.shots.map((shot) => (
              <div key={shot.id} className="shot-tile">
                <div className="thumbnail small">#{shot.shot_index}</div>
                <div className="muted tiny">
                  {formatTimecode(shot.start_time)} – {formatTimecode(shot.end_time)}
                </div>
                {shot.thumbnail_path ? (
                  <div className="muted tiny path">{shot.thumbnail_path}</div>
                ) : null}
              </div>
            ))}
          </div>
          {candidate.shots.length === 0 ? <p className="muted">이 구간과 겹치는 샷이 없습니다.</p> : null}
        </div>

        <div className="panel">
          <h2 className="section-title">Transcript Excerpt</h2>
          <div className="stack">
            {candidate.transcript_segments.map((segment) => (
              <div key={segment.id} className="timeline-block">
                <strong>
                  {formatTimecode(segment.start_time)} - {formatTimecode(segment.end_time)}
                </strong>
                <div>{segment.text}</div>
              </div>
            ))}
          </div>
        </div>

        <CandidateJobsAndDraftsLive
          candidateId={candidateId}
          initialJobs={jobs.items}
          initialDrafts={drafts.items}
        />
      </main>
    );
  } catch {
    notFound();
  }
}
