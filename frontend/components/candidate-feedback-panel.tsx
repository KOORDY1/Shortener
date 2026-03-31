"use client";

import { useCallback, useState } from "react";
import {
  createCandidateFeedback,
  getCandidateFeedbacks,
  setFailureTags
} from "@/lib/api";
import {
  FAILURE_TYPES,
  FAILURE_TYPE_LABELS,
  FEEDBACK_ACTIONS,
  FEEDBACK_ACTION_LABELS
} from "@/lib/types";
import type {
  CandidateFeedback,
  FailureType,
  FeedbackAction
} from "@/lib/types";

type Props = {
  candidateId: string;
  initialFailureTags: FailureType[];
};

export function CandidateFeedbackPanel({ candidateId, initialFailureTags }: Props) {
  const [failureTags, setFailureTagsState] = useState<FailureType[]>(initialFailureTags);
  const [feedbacks, setFeedbacks] = useState<CandidateFeedback[]>([]);
  const [feedbacksLoaded, setFeedbacksLoaded] = useState(false);
  const [saving, setSaving] = useState(false);
  const [feedbackAction, setFeedbackAction] = useState<FeedbackAction>("selected");
  const [feedbackReason, setFeedbackReason] = useState("");

  const toggleTag = useCallback(
    async (tag: FailureType) => {
      const next = failureTags.includes(tag)
        ? failureTags.filter((t) => t !== tag)
        : [...failureTags, tag];
      setFailureTagsState(next);
      setSaving(true);
      try {
        await setFailureTags(candidateId, next);
      } catch {
        setFailureTagsState(failureTags);
      } finally {
        setSaving(false);
      }
    },
    [candidateId, failureTags]
  );

  const loadFeedbacks = useCallback(async () => {
    const result = await getCandidateFeedbacks(candidateId);
    setFeedbacks(result.items);
    setFeedbacksLoaded(true);
  }, [candidateId]);

  const submitFeedback = useCallback(async () => {
    setSaving(true);
    try {
      await createCandidateFeedback(candidateId, {
        action: feedbackAction,
        reason: feedbackReason || undefined,
        failure_tags: failureTags
      });
      setFeedbackReason("");
      await loadFeedbacks();
    } finally {
      setSaving(false);
    }
  }, [candidateId, feedbackAction, feedbackReason, failureTags, loadFeedbacks]);

  return (
    <div className="panel">
      <h2 className="section-title">실패 유형 태깅</h2>
      <div className="tag-grid" style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
        {FAILURE_TYPES.map((tag) => (
          <button
            key={tag}
            type="button"
            className={failureTags.includes(tag) ? "tag-button active" : "tag-button"}
            onClick={() => toggleTag(tag)}
            disabled={saving}
            style={{
              padding: "0.25rem 0.75rem",
              borderRadius: "1rem",
              border: failureTags.includes(tag) ? "2px solid var(--accent, #0070f3)" : "1px solid #ccc",
              background: failureTags.includes(tag) ? "var(--accent-bg, #e8f4ff)" : "transparent",
              cursor: "pointer",
              fontSize: "0.85rem"
            }}
          >
            {FAILURE_TYPE_LABELS[tag]}
          </button>
        ))}
      </div>

      <h2 className="section-title" style={{ marginTop: "1.5rem" }}>운영자 피드백</h2>
      <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", flexWrap: "wrap" }}>
        <select
          value={feedbackAction}
          onChange={(e) => setFeedbackAction(e.target.value as FeedbackAction)}
          style={{ padding: "0.4rem" }}
        >
          {FEEDBACK_ACTIONS.map((action) => (
            <option key={action} value={action}>
              {FEEDBACK_ACTION_LABELS[action]}
            </option>
          ))}
        </select>
        <input
          type="text"
          placeholder="사유 (선택)"
          value={feedbackReason}
          onChange={(e) => setFeedbackReason(e.target.value)}
          style={{ flex: 1, minWidth: "12rem", padding: "0.4rem" }}
        />
        <button
          type="button"
          className="btn"
          onClick={submitFeedback}
          disabled={saving}
          style={{ padding: "0.4rem 1rem" }}
        >
          {saving ? "저장 중..." : "피드백 기록"}
        </button>
      </div>

      {!feedbacksLoaded ? (
        <button
          type="button"
          className="link-button"
          onClick={loadFeedbacks}
          style={{ marginTop: "0.75rem", fontSize: "0.85rem" }}
        >
          이전 피드백 보기
        </button>
      ) : feedbacks.length === 0 ? (
        <p className="muted" style={{ marginTop: "0.75rem" }}>기록된 피드백이 없습니다.</p>
      ) : (
        <div className="stack" style={{ marginTop: "0.75rem" }}>
          {feedbacks.map((fb) => (
            <div key={fb.id} className="timeline-block" style={{ fontSize: "0.85rem" }}>
              <strong>{FEEDBACK_ACTION_LABELS[fb.action] ?? fb.action}</strong>
              {fb.reason ? <span> — {fb.reason}</span> : null}
              {fb.failure_tags.length > 0 ? (
                <div className="muted" style={{ fontSize: "0.8rem" }}>
                  태그: {fb.failure_tags.map((t) => FAILURE_TYPE_LABELS[t] ?? t).join(", ")}
                </div>
              ) : null}
              <div className="muted tiny">{fb.created_at ?? ""}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
