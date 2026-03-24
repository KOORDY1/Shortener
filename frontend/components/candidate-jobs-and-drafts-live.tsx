"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { JobProgressStrip } from "@/components/job-progress-strip";
import { ScriptDraftCard } from "@/components/script-draft-card";
import {
  fetchJobsForCandidate,
  fetchScriptDraftsForCandidate,
  fetchVideoDraftsForCandidate
} from "@/lib/public-api";
import { Job, ScriptDraft, VideoDraftSummary } from "@/lib/types";

function hasActiveJobs(jobs: Job[]) {
  return jobs.some((job) => job.status === "queued" || job.status === "running");
}

function hasActiveScriptGenerationJob(jobs: Job[]) {
  return jobs.some(
    (job) =>
      job.type === "script_generation" && (job.status === "queued" || job.status === "running")
  );
}

type Props = {
  candidateId: string;
  initialJobs: Job[];
  initialDrafts: ScriptDraft[];
  initialVideoDrafts: VideoDraftSummary[];
};

export function CandidateJobsAndDraftsLive({
  candidateId,
  initialJobs,
  initialDrafts,
  initialVideoDrafts
}: Props) {
  const jobsQueryKey = ["jobs", "candidate", candidateId] as const;

  const { data: jobs = initialJobs } = useQuery({
    queryKey: jobsQueryKey,
    queryFn: () => fetchJobsForCandidate(candidateId),
    initialData: initialJobs,
    refetchInterval: (query) => (hasActiveJobs(query.state.data ?? []) ? 2000 : false)
  });

  const scriptJobActive = hasActiveScriptGenerationJob(jobs);

  const { data: drafts = initialDrafts } = useQuery({
    queryKey: ["scriptDrafts", candidateId],
    queryFn: () => fetchScriptDraftsForCandidate(candidateId),
    initialData: initialDrafts,
    refetchInterval: scriptJobActive ? 2000 : false
  });

  const { data: videoDrafts = initialVideoDrafts } = useQuery({
    queryKey: ["videoDrafts", candidateId],
    queryFn: () => fetchVideoDraftsForCandidate(candidateId),
    initialData: initialVideoDrafts
  });

  return (
    <>
      <JobProgressStrip jobs={jobs} />
      {videoDrafts.length > 0 ? (
        <div className="panel">
          <h2 className="section-title">Video drafts</h2>
          <ul className="stack" style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {videoDrafts.map((vd) => (
              <li key={vd.id} className="row spaced">
                <div>
                  <span className="muted">v{vd.version_no}</span>{" "}
                  <span>{vd.status}</span>
                  {vd.draft_video_path ? (
                    <div className="muted tiny path">{vd.draft_video_path}</div>
                  ) : null}
                </div>
                <Link href={`/drafts/${vd.id}`} className="link-button">
                  열기
                </Link>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      <div className="card-list">
        {drafts.map((draft) => (
          <ScriptDraftCard key={draft.id} draft={draft} candidateId={candidateId} />
        ))}
        {drafts.length === 0 ? (
          <div className="panel">
            <p className="muted">아직 생성된 script draft가 없습니다.</p>
          </div>
        ) : null}
      </div>
    </>
  );
}
