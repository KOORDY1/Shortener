import Link from "next/link";
import { CandidateSummary } from "@/lib/types";
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
      <div className="thumbnail">Candidate #{candidate.candidate_index}</div>
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
          <StatusBadge value={candidate.risk_level} />
        </div>
      </div>
      <div className="row">
        <div className="kpi">
          <span className="muted">Type</span>
          <strong>{candidate.type}</strong>
        </div>
        <div className="kpi">
          <span className="muted">Score</span>
          <strong>{candidate.total_score.toFixed(2)}</strong>
        </div>
        <div className="kpi">
          <span className="muted">Risk</span>
          <strong>{candidate.risk_score.toFixed(2)}</strong>
        </div>
      </div>
      <div className="row">
        <Link href={`/candidates/${candidate.id}`} className="link-button">
          Preview
        </Link>
        <CandidateGenerateScriptsButton candidateId={candidate.id} />
        <CandidateSelectButton candidateId={candidate.id} />
        <CandidateRejectButton candidateId={candidate.id} />
      </div>
    </div>
  );
}
