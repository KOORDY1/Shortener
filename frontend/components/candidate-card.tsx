import Link from "next/link";
import { FAILURE_TYPE_LABELS } from "@/lib/types";
import type { CandidateSummary, FailureType } from "@/lib/types";
import { badgeLabel } from "@/lib/labels";
import { formatDuration, formatTimecode } from "@/lib/format";
import { StatusBadge } from "@/components/status-badge";
import {
  CandidateGenerateScriptsButton,
  CandidateRejectButton,
  CandidateSelectButton
} from "@/components/mutation-buttons";

type Props = {
  candidate: CandidateSummary;
};

export function CandidateCard({ candidate }: Props) {
  return (
    <div className="candidate-card">
      <div className="thumbnail">후보 #{candidate.candidate_index}</div>
      <div className="spaced">
        <div className="stack">
          <strong>{candidate.title_hint}</strong>
          <span className="muted">
            {formatTimecode(candidate.start_time)} - {formatTimecode(candidate.end_time)} /{" "}
            {formatDuration(candidate.duration_seconds)}
          </span>
        </div>
        <div className="row">
          <StatusBadge value={candidate.status} />
          {candidate.selected ? <StatusBadge value="채택됨" /> : null}
          {candidate.composite ? <StatusBadge value="composite" /> : null}
        </div>
      </div>
      <div className="row">
        <div className="kpi">
          <span className="muted">유형</span>
          <strong>{badgeLabel(candidate.type)}</strong>
        </div>
        <div className="kpi">
          <span className="muted">총점</span>
          <strong>{candidate.total_score.toFixed(2)}</strong>
        </div>
        <div className="kpi">
          <span className="muted">Span</span>
          <strong>{candidate.span_count ?? 1}</strong>
        </div>
      </div>
      {candidate.failure_tags.length > 0 ? (
        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.25rem" }}>
          {candidate.failure_tags.map((tag) => (
            <span
              key={tag}
              style={{
                padding: "0.1rem 0.4rem",
                borderRadius: "0.5rem",
                fontSize: "0.7rem",
                background: "#fef2f2",
                color: "#991b1b",
                border: "1px solid #fecaca"
              }}
            >
              {FAILURE_TYPE_LABELS[tag as FailureType] ?? tag}
            </span>
          ))}
        </div>
      ) : null}
      <div className="row">
        <Link href={`/candidates/${candidate.id}`} className="link-button">
          미리보기
        </Link>
        <CandidateGenerateScriptsButton candidateId={candidate.id} />
        <CandidateSelectButton candidateId={candidate.id} />
        <CandidateRejectButton candidateId={candidate.id} />
      </div>
    </div>
  );
}
