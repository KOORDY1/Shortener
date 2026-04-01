"use client";

import { useCallback, useEffect, useState } from "react";
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

/** 액션별 설명 — 운영자에게 의도를 명확하게 전달 */
const ACTION_DESCRIPTIONS: Record<FeedbackAction, string> = {
  selected: "이 후보를 쇼츠로 채택합니다 (상태 → selected)",
  rejected: "이 후보를 탈락시킵니다 (상태 → rejected)",
  edited: "트림/수정 의도를 기록합니다",
  reordered: "목표 순위를 입력하면 에피소드 전체 순위가 재정렬됩니다"
};

type Props = {
  candidateId: string;
  initialFailureTags: FailureType[];
  candidateStatus: string;
  candidateSelected: boolean;
  onStatusChange?: (status: string, selected: boolean) => void;
};

export function CandidateFeedbackPanel({
  candidateId,
  initialFailureTags,
  candidateStatus,
  candidateSelected,
  onStatusChange
}: Props) {
  const [failureTags, setFailureTagsState] = useState<FailureType[]>(initialFailureTags);
  const [feedbacks, setFeedbacks] = useState<CandidateFeedback[]>([]);
  const [feedbacksLoaded, setFeedbacksLoaded] = useState(false);
  const [saving, setSaving] = useState(false);
  const [feedbackAction, setFeedbackAction] = useState<FeedbackAction>("selected");
  const [feedbackReason, setFeedbackReason] = useState("");
  const [submitResult, setSubmitResult] = useState<{ ok: boolean; message: string } | null>(null);
  const [currentStatus, setCurrentStatus] = useState(candidateStatus);
  const [currentSelected, setCurrentSelected] = useState(candidateSelected);
  const [newRank, setNewRank] = useState("");

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

  const [feedbackLoadError, setFeedbackLoadError] = useState(false);

  const loadFeedbacks = useCallback(async () => {
    try {
      setFeedbackLoadError(false);
      const result = await getCandidateFeedbacks(candidateId);
      setFeedbacks(result.items);
      setFeedbacksLoaded(true);
    } catch {
      setFeedbackLoadError(true);
      setFeedbacksLoaded(true);
    }
  }, [candidateId]);

  // 초기 자동 로드
  useEffect(() => {
    void loadFeedbacks();
  }, [loadFeedbacks]);

  const submitFeedback = useCallback(async () => {
    // reordered일 때 new_rank 필수 검증
    if (feedbackAction === "reordered" && (newRank === "" || isNaN(parseInt(newRank, 10)))) {
      setSubmitResult({ ok: false, message: "새 순위를 입력하세요" });
      return;
    }
    setSaving(true);
    setSubmitResult(null);
    try {
      const metadata: Record<string, string | number | boolean | null> =
        feedbackAction === "reordered" && newRank !== ""
          ? { new_rank: parseInt(newRank, 10) }
          : {};
      const fb = await createCandidateFeedback(candidateId, {
        action: feedbackAction,
        reason: feedbackReason || undefined,
        failure_tags: failureTags,
        metadata
      });
      setFeedbackReason("");
      setNewRank("");

      // reordered 성공 메시지에 from→to 포함
      let successMsg = `${FEEDBACK_ACTION_LABELS[feedbackAction]} 완료`;
      if (feedbackAction === "reordered") {
        const from = fb.metadata.reorder_from;
        const to = fb.metadata.reorder_to;
        if (typeof from === "number" && typeof to === "number") {
          successMsg = `${from}위 → ${to}위 이동 완료`;
        }
      }
      setSubmitResult({ ok: true, message: successMsg });

      // 상태 반영
      const afterStatus = fb.after_snapshot.status;
      const afterSelected = fb.after_snapshot.selected;
      setCurrentStatus(afterStatus);
      setCurrentSelected(afterSelected);
      onStatusChange?.(afterStatus, afterSelected);

      await loadFeedbacks();
    } catch (e) {
      const msg = e instanceof Error ? e.message : "알 수 없는 오류";
      setSubmitResult({ ok: false, message: msg });
    } finally {
      setSaving(false);
    }
  }, [candidateId, feedbackAction, feedbackReason, failureTags, newRank, loadFeedbacks, onStatusChange]);

  return (
    <div className="panel">
      {/* 현재 상태 배지 */}
      <div style={{ display: "flex", gap: "0.75rem", alignItems: "center", marginBottom: "1rem" }}>
        <span style={{ fontSize: "0.85rem" }} className="muted">현재 상태:</span>
        <span
          style={{
            padding: "0.2rem 0.6rem",
            borderRadius: "0.25rem",
            fontSize: "0.8rem",
            fontWeight: 600,
            background: currentSelected ? "#dcfce7" : currentStatus === "rejected" ? "#fee2e2" : "#f3f4f6",
            color: currentSelected ? "#166534" : currentStatus === "rejected" ? "#991b1b" : "#374151"
          }}
        >
          {currentStatus}{currentSelected ? " (채택)" : ""}
        </span>
      </div>

      <h2 className="section-title">실패 유형 태깅</h2>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
        {FAILURE_TYPES.map((tag) => (
          <button
            key={tag}
            type="button"
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

      {/* 액션 선택 + 설명 */}
      <div style={{ display: "flex", gap: "0.5rem", alignItems: "flex-start", flexWrap: "wrap" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
          <select
            value={feedbackAction}
            onChange={(e) => {
              setFeedbackAction(e.target.value as FeedbackAction);
              setSubmitResult(null);
            }}
            style={{ padding: "0.4rem" }}
          >
            {FEEDBACK_ACTIONS.map((action) => (
              <option key={action} value={action}>
                {FEEDBACK_ACTION_LABELS[action]}
              </option>
            ))}
          </select>
          <span className="muted" style={{ fontSize: "0.75rem" }}>
            {ACTION_DESCRIPTIONS[feedbackAction]}
          </span>
        </div>
        {feedbackAction === "reordered" ? (
          <input
            type="number"
            min={1}
            placeholder="목표 순위"
            value={newRank}
            onChange={(e) => setNewRank(e.target.value)}
            style={{ width: "5rem", padding: "0.4rem" }}
          />
        ) : null}
        <input
          type="text"
          placeholder="사유 (선택)"
          value={feedbackReason}
          onChange={(e) => setFeedbackReason(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !saving) void submitFeedback();
          }}
          style={{ flex: 1, minWidth: "12rem", padding: "0.4rem" }}
        />
        <button
          type="button"
          onClick={submitFeedback}
          disabled={saving}
          style={{
            padding: "0.4rem 1rem",
            background: feedbackAction === "rejected" ? "#ef4444" : "#2563eb",
            color: "#fff",
            border: "none",
            borderRadius: "0.25rem",
            cursor: saving ? "wait" : "pointer",
            fontWeight: 500
          }}
        >
          {saving ? "저장 중…" : FEEDBACK_ACTION_LABELS[feedbackAction]}
        </button>
      </div>

      {/* 성공/실패 표시 */}
      {submitResult ? (
        <div
          style={{
            marginTop: "0.5rem",
            padding: "0.3rem 0.75rem",
            borderRadius: "0.25rem",
            fontSize: "0.85rem",
            background: submitResult.ok ? "#dcfce7" : "#fee2e2",
            color: submitResult.ok ? "#166534" : "#991b1b"
          }}
        >
          {submitResult.ok ? "✓" : "✗"} {submitResult.message}
        </div>
      ) : null}

      {/* 피드백 이력 */}
      <h3 className="section-title" style={{ marginTop: "1.25rem", fontSize: "0.9rem" }}>
        피드백 이력 {feedbacksLoaded ? `(${feedbacks.length}건)` : ""}
      </h3>
      {!feedbacksLoaded ? (
        <p className="muted" style={{ fontSize: "0.85rem" }}>불러오는 중…</p>
      ) : feedbackLoadError ? (
        <p style={{ fontSize: "0.85rem", color: "#991b1b" }}>피드백 이력을 불러오지 못했습니다.</p>
      ) : feedbacks.length === 0 ? (
        <p className="muted" style={{ fontSize: "0.85rem" }}>기록된 피드백이 없습니다.</p>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
          {feedbacks.map((fb) => (
            <div
              key={fb.id}
              style={{
                padding: "0.5rem 0.75rem",
                borderRadius: "0.25rem",
                fontSize: "0.85rem",
                background:
                  fb.action === "selected"
                    ? "#f0fdf4"
                    : fb.action === "rejected"
                      ? "#fef2f2"
                      : "#f9fafb",
                borderLeft: `3px solid ${
                  fb.action === "selected"
                    ? "#22c55e"
                    : fb.action === "rejected"
                      ? "#ef4444"
                      : "#9ca3af"
                }`
              }}
            >
              <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
                <strong>{FEEDBACK_ACTION_LABELS[fb.action] ?? fb.action}</strong>
                {fb.reason ? <span className="muted">— {fb.reason}</span> : null}
              </div>
              {/* 상태 전이 */}
              {fb.before_snapshot.status !== fb.after_snapshot.status ? (
                <div className="muted" style={{ fontSize: "0.8rem" }}>
                  상태: {fb.before_snapshot.status} → {fb.after_snapshot.status}
                </div>
              ) : null}
              {fb.action === "reordered" && fb.before_snapshot.candidate_index !== fb.after_snapshot.candidate_index ? (
                <div className="muted" style={{ fontSize: "0.8rem" }}>
                  순위: #{fb.before_snapshot.candidate_index} → #{fb.after_snapshot.candidate_index}
                </div>
              ) : null}
              {fb.failure_tags.length > 0 ? (
                <div className="muted" style={{ fontSize: "0.8rem" }}>
                  태그: {fb.failure_tags.map((t) => FAILURE_TYPE_LABELS[t] ?? t).join(", ")}
                </div>
              ) : null}
              <div className="muted" style={{ fontSize: "0.75rem" }}>{fb.created_at ?? ""}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
