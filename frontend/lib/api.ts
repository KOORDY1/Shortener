import {
  CandidateDetail,
  CandidateFeedbackListResponse,
  CandidateListResponse,
  Episode,
  EpisodeListResponse,
  EpisodeOperationOkResponse,
  EpisodeTimeline,
  ExportDetail,
  FailureTagResponse,
  FailureType,
  FeedbackAction,
  JobListResponse,
  ScriptDraftListResponse,
  VideoDraftDetail,
  VideoDraftListResponse
} from "@/lib/types";

const apiBaseUrl =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

/** HTTP 상태를 보존해 서버 컴포넌트에서 404와 5xx를 구분할 수 있게 합니다. */
export class ApiHttpError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiHttpError";
    this.status = status;
  }
}

function apiRootDisplay(): string {
  return apiBaseUrl.replace(/\/api\/v1\/?$/, "") || apiBaseUrl;
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${apiBaseUrl}${path}`;
  let response: Response;
  try {
    response = await fetch(url, {
      ...init,
      cache: "no-store"
    });
  } catch (e) {
    const inner =
      e instanceof Error && e.cause instanceof Error
        ? `${e.message} — ${e.cause.message}`
        : e instanceof Error
          ? e.message
          : String(e);
    throw new Error(
      `API에 연결하지 못했습니다 (${url}). ` +
        `백엔드가 ${apiRootDisplay()} 에서 실행 중인지 확인하세요 ` +
        `(예: docker compose up backend-api, 또는 uvicorn). 원인: ${inner}`
    );
  }
  if (!response.ok) {
    throw new ApiHttpError(
      response.status,
      `API request failed: ${response.status} ${response.statusText}`
    );
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

export async function deleteEpisode(episodeId: string): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/episodes/${episodeId}`, {
    method: "DELETE",
    cache: "no-store"
  });
  if (!response.ok) {
    throw new ApiHttpError(
      response.status,
      `API request failed: ${response.status} ${response.statusText}`
    );
  }
}

export async function clearEpisodeAnalysis(episodeId: string): Promise<EpisodeOperationOkResponse> {
  const response = await fetch(`${apiBaseUrl}/episodes/${episodeId}/clear-analysis`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
    cache: "no-store"
  });
  if (!response.ok) {
    throw new ApiHttpError(
      response.status,
      `API request failed: ${response.status} ${response.statusText}`
    );
  }
  return (await response.json()) as EpisodeOperationOkResponse;
}

export async function clearEpisodeCache(episodeId: string): Promise<EpisodeOperationOkResponse> {
  const response = await fetch(`${apiBaseUrl}/episodes/${episodeId}/clear-cache`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
    cache: "no-store"
  });
  if (!response.ok) {
    throw new ApiHttpError(
      response.status,
      `API request failed: ${response.status} ${response.statusText}`
    );
  }
  return (await response.json()) as EpisodeOperationOkResponse;
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
    type?: string;
    sort_by?: string;
    order?: string;
  }
): Promise<CandidateListResponse> {
  const query = new URLSearchParams();
  if (filters?.status) query.set("status", filters.status);
  if (filters?.min_score) query.set("min_score", filters.min_score);
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
  job_type?: string;
  status?: string;
  page?: number;
  page_size?: number;
}): Promise<JobListResponse> {
  const query = new URLSearchParams();
  if (filters?.episode_id) query.set("episode_id", filters.episode_id);
  if (filters?.candidate_id) query.set("candidate_id", filters.candidate_id);
  if (filters?.job_type) query.set("job_type", filters.job_type);
  if (filters?.status) query.set("status", filters.status);
  if (filters?.page != null) query.set("page", String(filters.page));
  if (filters?.page_size != null) query.set("page_size", String(filters.page_size));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiFetch<JobListResponse>(`/jobs${suffix}`);
}

export async function getCandidateVideoDrafts(candidateId: string): Promise<VideoDraftListResponse> {
  return apiFetch<VideoDraftListResponse>(`/candidates/${candidateId}/video-drafts`);
}

export async function getVideoDraft(videoDraftId: string): Promise<VideoDraftDetail> {
  return apiFetch<VideoDraftDetail>(`/video-drafts/${videoDraftId}`);
}

export async function getExport(exportId: string): Promise<ExportDetail> {
  return apiFetch<ExportDetail>(`/exports/${exportId}`);
}

// --- 실패 유형 태깅 ---

export async function getFailureTags(candidateId: string): Promise<FailureTagResponse> {
  return apiFetch<FailureTagResponse>(`/candidates/${candidateId}/failure-tags`);
}

export async function setFailureTags(
  candidateId: string,
  failureTags: FailureType[]
): Promise<FailureTagResponse> {
  const response = await fetch(`${apiBaseUrl}/candidates/${candidateId}/failure-tags`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ failure_tags: failureTags }),
    cache: "no-store"
  });
  if (!response.ok) {
    throw new ApiHttpError(
      response.status,
      `API request failed: ${response.status} ${response.statusText}`
    );
  }
  return (await response.json()) as FailureTagResponse;
}

// --- 운영자 피드백 로그 ---

export async function getCandidateFeedbacks(
  candidateId: string
): Promise<CandidateFeedbackListResponse> {
  return apiFetch<CandidateFeedbackListResponse>(
    `/candidates/${candidateId}/feedbacks`
  );
}

export async function createCandidateFeedback(
  candidateId: string,
  payload: {
    action: FeedbackAction;
    reason?: string;
    failure_tags?: FailureType[];
    metadata?: Record<string, unknown>;
  }
): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/candidates/${candidateId}/feedbacks`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    cache: "no-store"
  });
  if (!response.ok) {
    throw new ApiHttpError(
      response.status,
      `API request failed: ${response.status} ${response.statusText}`
    );
  }
}

export { apiBaseUrl };
