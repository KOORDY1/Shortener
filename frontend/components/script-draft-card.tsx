import { ScriptDraft } from "@/lib/types";
import { StatusBadge } from "@/components/status-badge";
import {
  CreateVideoDraftFromScriptButton,
  SelectScriptDraftButton,
  UpdateScriptDraftForm
} from "@/components/mutation-buttons";

type Props = {
  draft: ScriptDraft;
  candidateId: string;
};

export function ScriptDraftCard({ draft, candidateId }: Props) {
  return (
    <div className="draft-card">
      <div className="spaced">
        <strong>버전 {draft.version_no}</strong>
        {draft.is_selected ? <StatusBadge value="selected" /> : null}
      </div>
      <div className="stack">
        <div>
          <span className="muted">훅</span>
          <p>{draft.hook_text}</p>
        </div>
        <div>
          <span className="muted">본문</span>
          <p>{draft.body_text}</p>
        </div>
        <div>
          <span className="muted">CTA</span>
          <p>{draft.cta_text}</p>
        </div>
        <div>
          <span className="muted">제목 후보</span>
          <p>{draft.title_options.join(" / ")}</p>
        </div>
      </div>
      <div className="row">
        <SelectScriptDraftButton scriptDraftId={draft.id} />
        <CreateVideoDraftFromScriptButton candidateId={candidateId} scriptDraftId={draft.id} />
      </div>
      <UpdateScriptDraftForm draft={draft} />
    </div>
  );
}
