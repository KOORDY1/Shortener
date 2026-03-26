"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { apiBaseUrl, clearEpisodeAnalysis, clearEpisodeCache, deleteEpisode } from "@/lib/api";
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
      {loading ? "실행 중…" : "분석"}
    </button>
  );
}

export function FullReanalyzeEpisodeButton({ episodeId }: { episodeId: string }) {
  const { loading, run } = useAction();
  return (
    <button
      className="button ghost"
      disabled={loading}
      type="button"
      onClick={() => {
        if (
          !window.confirm(
            "프록시/샷/키프레임/비전 캐시를 모두 무시하고 처음부터 다시 분석합니다.\n시간과 비용이 더 들 수 있습니다.\n계속할까요?"
          )
        ) {
          return;
        }
        run(async () => {
          await request(`/episodes/${episodeId}/analyze`, {
            method: "POST",
            body: JSON.stringify({
              force_reanalyze: true,
              ignore_cache: true
            })
          });
        });
      }}
    >
      {loading ? "재분석 중…" : "완전 재분석"}
    </button>
  );
}

export function ClearEpisodeAnalysisButton({ episodeId }: { episodeId: string }) {
  const { loading, run } = useAction();
  return (
    <button
      className="button ghost"
      disabled={loading}
      type="button"
      onClick={() => {
        if (
          !window.confirm(
            "이 에피소드의 분석 결과를 모두 지웁니다.\n(후보·샷·대본·작업 기록·쇼츠/렌더 파일 등. 원본 업로드 영상은 유지됩니다.)\n계속할까요?"
          )
        ) {
          return;
        }
        run(async () => {
          await clearEpisodeAnalysis(episodeId);
        });
      }}
    >
      {loading ? "삭제 중…" : "분석 결과 삭제"}
    </button>
  );
}

export function ClearEpisodeCacheButton({ episodeId }: { episodeId: string }) {
  const { loading, run } = useAction();
  return (
    <button
      className="button ghost"
      disabled={loading}
      type="button"
      onClick={() => {
        if (
          !window.confirm(
            "이 에피소드의 분석 가속용 캐시만 지웁니다.\n(proxy/audio/shots/cache)\n현재 후보/대본은 유지되지만 샷 타임라인과 캐시 기반 미리보기는 다음 재분석 전까지 비어 있을 수 있습니다.\n계속할까요?"
          )
        ) {
          return;
        }
        run(async () => {
          await clearEpisodeCache(episodeId);
        });
      }}
    >
      {loading ? "삭제 중…" : "캐시 삭제"}
    </button>
  );
}

export function DeleteEpisodeButton({ episodeId }: { episodeId: string }) {
  const router = useRouter();
  const [loading, setLoading] = useState(false);

  return (
    <button
      className="button danger"
      disabled={loading}
      type="button"
      onClick={() => {
        if (
          !window.confirm(
            "에피소드를 완전히 삭제합니다.\nDB 기록·업로드 파일·분석 산출물이 모두 사라집니다.\n이 작업은 되돌릴 수 없습니다. 계속할까요?"
          )
        ) {
          return;
        }
        void (async () => {
          setLoading(true);
          try {
            await deleteEpisode(episodeId);
            router.push("/episodes");
            router.refresh();
          } catch {
            window.alert("삭제에 실패했습니다. API 로그를 확인하세요.");
          } finally {
            setLoading(false);
          }
        })();
      }}
    >
      {loading ? "삭제 중…" : "에피소드 삭제"}
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
      {loading ? "생성 중…" : "스크립트 생성"}
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
      {loading ? "처리 중…" : "선택"}
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
      {loading ? "처리 중…" : "거절"}
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
              template_type: "dramashorts_v1",
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
      {loading ? "처리 중…" : "이 초안 선택"}
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
        <label>훅</label>
        <input className="input" value={hookText} onChange={(event) => setHookText(event.target.value)} />
      </div>
      <div className="field">
        <label>본문</label>
        <textarea className="textarea" value={bodyText} onChange={(event) => setBodyText(event.target.value)} />
      </div>
      <div className="field">
        <label>행동 유도(CTA)</label>
        <input className="input" value={ctaText} onChange={(event) => setCtaText(event.target.value)} />
      </div>
      <div className="field">
        <label>제목 후보</label>
        <textarea className="textarea" value={titles} onChange={(event) => setTitles(event.target.value)} />
      </div>
      <button className="button ghost" type="submit" disabled={loading}>
        {loading ? "저장 중…" : "초안 저장"}
      </button>
    </form>
  );
}
