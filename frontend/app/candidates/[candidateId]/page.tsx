import { notFound } from "next/navigation";
import { CandidateDetailContent } from "@/components/candidate-detail-content";
import {
  ApiHttpError,
  getCandidate,
  getCandidateScriptDrafts,
  getCandidateVideoDrafts,
  getFailureTags,
  getJobs
} from "@/lib/api";
import type { FailureType } from "@/lib/types";

export default async function CandidateDetailPage({
  params
}: {
  params: Promise<{ candidateId: string }>;
}) {
  const { candidateId } = await params;
  const [candidate, drafts, jobs, videoDrafts, failureTagsResult] = await Promise.all([
    getCandidate(candidateId),
    getCandidateScriptDrafts(candidateId),
    getJobs({ candidate_id: candidateId }),
    getCandidateVideoDrafts(candidateId),
    getFailureTags(candidateId).catch(() => ({ id: candidateId, failure_tags: [] as FailureType[] }))
  ]).catch((e: unknown) => {
    if (e instanceof ApiHttpError && e.status === 404) {
      notFound();
    }
    throw e;
  });

  return (
    <CandidateDetailContent
      key={`${candidateId}:${candidate.render_config?.trim_start ?? candidate.start_time}:${
        candidate.render_config?.trim_end ?? candidate.end_time
      }`}
      candidateId={candidateId}
      candidate={candidate}
      drafts={drafts.items}
      jobs={jobs.items}
      videoDrafts={videoDrafts.items}
      initialFailureTags={failureTagsResult.failure_tags}
    />
  );
}
