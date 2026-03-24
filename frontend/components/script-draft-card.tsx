import { ScriptDraft } from "@/lib/types";
import { StatusBadge } from "@/components/status-badge";
import { SelectScriptDraftButton, UpdateScriptDraftForm } from "@/components/mutation-buttons";

type Props = {
  draft: ScriptDraft;
};

export function ScriptDraftCard({ draft }: Props) {
  return (
    <div className="draft-card">
      <div className="spaced">
        <strong>Version {draft.version_no}</strong>
        {draft.is_selected ? <StatusBadge value="selected" /> : null}
      </div>
      <div className="stack">
        <div>
          <span className="muted">Hook</span>
          <p>{draft.hook_text}</p>
        </div>
        <div>
          <span className="muted">Body</span>
          <p>{draft.body_text}</p>
        </div>
        <div>
          <span className="muted">CTA</span>
          <p>{draft.cta_text}</p>
        </div>
        <div>
          <span className="muted">Titles</span>
          <p>{draft.title_options.join(" / ")}</p>
        </div>
      </div>
      <div className="row">
        <SelectScriptDraftButton scriptDraftId={draft.id} />
      </div>
      <UpdateScriptDraftForm draft={draft} />
    </div>
  );
}
