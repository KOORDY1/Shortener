"use client";

import { useQuery } from "@tanstack/react-query";
import { JobProgressStrip } from "@/components/job-progress-strip";
import { ScriptDraftCard } from "@/components/script-draft-card";
import { fetchJobsForCandidate, fetchScriptDraftsForCandidate } from "@/lib/public-api";
import { Job, ScriptDraft } from "@/lib/types";

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
};

export function CandidateJobsAndDraftsLive({
  candidateId,
  initialJobs,
  initialDrafts
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

  return (
    <>
      <JobProgressStrip jobs={jobs} />
      <div className="card-list">
        {drafts.map((draft) => (
          <ScriptDraftCard key={draft.id} draft={draft} />
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
