import {
  CandidateDetail,
  CandidateListResponse,
  Episode,
  EpisodeListResponse,
  EpisodeTimeline,
  Job,
  JobListResponse,
  ScriptDraftListResponse
} from "@/lib/types";

const apiBaseUrl =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    ...init,
    cache: "no-store"
  });
  if (!response.ok) {
    throw new Error(`API request failed: ${response.status} ${response.statusText}`);
  }
  return (await response.json()) as T;
}

export async function getEpisodes(searchParams?: {
  status?: string;
  show_title?: string;
}): Promise<EpisodeListResponse> {
  const query = new URLSearchParams();
  if (searchParams?.status) query.set("status", searchParams.status);
  if (searchParams?.show_title) query.set("show_title", searchParams.show_title);
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiFetch<EpisodeListResponse>(`/episodes${suffix}`);
}

export async function getEpisode(episodeId: string): Promise<Episode> {
  return apiFetch<Episode>(`/episodes/${episodeId}`);
}

export async function getEpisodeTimeline(episodeId: string): Promise<EpisodeTimeline> {
  return apiFetch<EpisodeTimeline>(`/episodes/${episodeId}/timeline`);
}

export async function getEpisodeJobs(episodeId: string): Promise<JobListResponse> {
  return apiFetch<JobListResponse>(`/episodes/${episodeId}/jobs`);
}

export async function getEpisodeCandidates(
  episodeId: string,
  filters?: {
    status?: string;
    min_score?: string;
    risk_level?: string;
    type?: string;
    sort_by?: string;
    order?: string;
  }
): Promise<CandidateListResponse> {
  const query = new URLSearchParams();
  if (filters?.status) query.set("status", filters.status);
  if (filters?.min_score) query.set("min_score", filters.min_score);
  if (filters?.risk_level) query.set("risk_level", filters.risk_level);
  if (filters?.type) query.set("type", filters.type);
  if (filters?.sort_by) query.set("sort_by", filters.sort_by);
  if (filters?.order) query.set("order", filters.order);
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiFetch<CandidateListResponse>(`/episodes/${episodeId}/candidates${suffix}`);
}

export async function getCandidate(candidateId: string): Promise<CandidateDetail> {
  return apiFetch<CandidateDetail>(`/candidates/${candidateId}`);
}

export async function getCandidateScriptDrafts(candidateId: string): Promise<ScriptDraftListResponse> {
  return apiFetch<ScriptDraftListResponse>(`/candidates/${candidateId}/script-drafts`);
}

export async function getJobs(filters?: {
  episode_id?: string;
  candidate_id?: string;
}): Promise<JobListResponse> {
  const query = new URLSearchParams();
  if (filters?.episode_id) query.set("episode_id", filters.episode_id);
  if (filters?.candidate_id) query.set("candidate_id", filters.candidate_id);
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiFetch<JobListResponse>(`/jobs${suffix}`);
}

export { apiBaseUrl };
