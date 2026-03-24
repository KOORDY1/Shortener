"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { apiBaseUrl } from "@/lib/api";
import { ScriptDraft } from "@/lib/types";

async function request(path: string, init?: RequestInit) {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {})
    }
  });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json().catch(() => null);
}

function useAction() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);

  async function run(action: () => Promise<void>) {
    setLoading(true);
    try {
      await action();
      router.refresh();
    } finally {
      setLoading(false);
    }
  }

  return { loading, run };
}

export function AnalyzeEpisodeButton({ episodeId }: { episodeId: string }) {
  const { loading, run } = useAction();
  return (
    <button
      className="button"
      disabled={loading}
      onClick={() =>
        run(async () => {
          await request(`/episodes/${episodeId}/analyze`, {
            method: "POST",
            body: JSON.stringify({ force_reanalyze: false })
          });
        })
      }
    >
      {loading ? "Running..." : "Analyze"}
    </button>
  );
}

export function CandidateGenerateScriptsButton({ candidateId }: { candidateId: string }) {
  const { loading, run } = useAction();
  return (
    <button
      className="button"
      disabled={loading}
      onClick={() =>
        run(async () => {
          await request(`/candidates/${candidateId}/script-drafts`, {
            method: "POST",
            body: JSON.stringify({
              language: "ko",
              versions: 2,
              tone: "sharp_explanatory",
              channel_style: "kr_us_drama",
              force_regenerate: true
            })
          });
        })
      }
    >
      {loading ? "Generating..." : "Generate Scripts"}
    </button>
  );
}

export function CandidateSelectButton({ candidateId }: { candidateId: string }) {
  const { loading, run } = useAction();
  return (
    <button
      className="button"
      disabled={loading}
      onClick={() =>
        run(async () => {
          await request(`/candidates/${candidateId}/select`, {
            method: "POST",
            body: JSON.stringify({ selected: true })
          });
        })
      }
    >
      Select
    </button>
  );
}

export function CandidateRejectButton({ candidateId }: { candidateId: string }) {
  const { loading, run } = useAction();
  return (
    <button
      className="button danger"
      disabled={loading}
      onClick={() =>
        run(async () => {
          await request(`/candidates/${candidateId}/reject`, {
            method: "POST",
            body: JSON.stringify({ reason: "operator_rejected" })
          });
        })
      }
    >
      Reject
    </button>
  );
}

export function CreateVideoDraftFromScriptButton({
  candidateId,
  scriptDraftId
}: {
  candidateId: string;
  scriptDraftId: string;
}) {
  const router = useRouter();
  const [loading, setLoading] = useState(false);

  return (
    <button
      className="button ghost"
      disabled={loading}
      onClick={async () => {
        setLoading(true);
        try {
          const data = (await request(`/candidates/${candidateId}/video-drafts`, {
            method: "POST",
            body: JSON.stringify({
              script_draft_id: scriptDraftId,
              template_type: "context_commentary_v1",
              burned_caption: true
            })
          })) as { video_draft_id?: string | null };
          if (data?.video_draft_id) {
            router.push(`/drafts/${data.video_draft_id}`);
          } else {
            router.refresh();
          }
        } finally {
          setLoading(false);
        }
      }}
    >
      {loading ? "생성 중…" : "비디오 초안 만들기"}
    </button>
  );
}

export function SelectScriptDraftButton({ scriptDraftId }: { scriptDraftId: string }) {
  const { loading, run } = useAction();
  return (
    <button
      className="button"
      disabled={loading}
      onClick={() =>
        run(async () => {
          await request(`/script-drafts/${scriptDraftId}/select`, {
            method: "POST"
          });
        })
      }
    >
      {loading ? "Selecting..." : "Select Draft"}
    </button>
  );
}

export function UpdateScriptDraftForm({ draft }: { draft: ScriptDraft }) {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [hookText, setHookText] = useState(draft.hook_text);
  const [bodyText, setBodyText] = useState(draft.body_text);
  const [ctaText, setCtaText] = useState(draft.cta_text);
  const [titles, setTitles] = useState(draft.title_options.join("\n"));

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    try {
      await request(`/script-drafts/${draft.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          hook_text: hookText,
          body_text: bodyText,
          cta_text: ctaText,
          title_options: titles
            .split("\n")
            .map((item) => item.trim())
            .filter(Boolean)
        })
      });
      router.refresh();
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="stack">
      <div className="field">
        <label>Hook</label>
        <input className="input" value={hookText} onChange={(event) => setHookText(event.target.value)} />
      </div>
      <div className="field">
        <label>Body</label>
        <textarea className="textarea" value={bodyText} onChange={(event) => setBodyText(event.target.value)} />
      </div>
      <div className="field">
        <label>CTA</label>
        <input className="input" value={ctaText} onChange={(event) => setCtaText(event.target.value)} />
      </div>
      <div className="field">
        <label>Titles</label>
        <textarea className="textarea" value={titles} onChange={(event) => setTitles(event.target.value)} />
      </div>
      <button className="button ghost" type="submit" disabled={loading}>
        {loading ? "Saving..." : "Save Draft Copy"}
      </button>
    </form>
  );
}
