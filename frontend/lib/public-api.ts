import { apiBaseUrl } from "@/lib/api";
import { Job, ScriptDraft } from "@/lib/types";

export async function fetchJobsForEpisode(episodeId: string): Promise<Job[]> {
  const response = await fetch(`${apiBaseUrl}/episodes/${episodeId}/jobs`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`episode jobs fetch failed: ${response.status}`);
  }
  const data = (await response.json()) as { items: Job[] };
  return data.items;
}

export async function fetchJobsForCandidate(candidateId: string): Promise<Job[]> {
  const response = await fetch(`${apiBaseUrl}/jobs?candidate_id=${encodeURIComponent(candidateId)}`, {
    cache: "no-store"
  });
  if (!response.ok) {
    throw new Error(`jobs fetch failed: ${response.status}`);
  }
  const data = (await response.json()) as { items: Job[] };
  return data.items;
}

export async function fetchScriptDraftsForCandidate(candidateId: string): Promise<ScriptDraft[]> {
  const response = await fetch(`${apiBaseUrl}/candidates/${candidateId}/script-drafts`, {
    cache: "no-store"
  });
  if (!response.ok) {
    throw new Error(`script drafts fetch failed: ${response.status}`);
  }
  const data = (await response.json()) as { items: ScriptDraft[] };
  return data.items;
}
