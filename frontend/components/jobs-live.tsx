"use client";

import { useQuery } from "@tanstack/react-query";
import { JobProgressStrip } from "@/components/job-progress-strip";
import { fetchJobsForCandidate, fetchJobsForEpisode } from "@/lib/public-api";
import { Job } from "@/lib/types";

function hasActiveJobs(jobs: Job[]) {
  return jobs.some((job) => job.status === "queued" || job.status === "running");
}

type EpisodeScope = {
  initialJobs: Job[];
  episodeId: string;
};

type CandidateScope = {
  initialJobs: Job[];
  candidateId: string;
};

type Props = EpisodeScope | CandidateScope;

export function JobsLiveStrip(props: Props) {
  const { initialJobs } = props;

  const queryKey =
    "episodeId" in props
      ? (["jobs", "episode", props.episodeId] as const)
      : (["jobs", "candidate", props.candidateId] as const);

  const queryFn =
    "episodeId" in props
      ? () => fetchJobsForEpisode(props.episodeId)
      : () => fetchJobsForCandidate(props.candidateId);

  const { data = initialJobs } = useQuery({
    queryKey,
    queryFn,
    initialData: initialJobs,
    refetchInterval: (query) => (hasActiveJobs(query.state.data ?? []) ? 2000 : false)
  });

  return <JobProgressStrip jobs={data} />;
}
