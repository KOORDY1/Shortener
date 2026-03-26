"use client";

type Props = {
  assBusy: boolean;
  assMsg: string | null;
  assText: string;
  onAssTextChange: (value: string) => void;
  onDownloadAss: () => void;
  onSaveEditedAss: () => void;
};

export function AssEditor({
  assBusy,
  assMsg,
  assText,
  onAssTextChange,
  onDownloadAss,
  onSaveEditedAss
}: Props) {
  return (
    <div className="stack" style={{ marginTop: 12 }}>
      <div className="row wrap">
        <button type="button" className="button ghost" onClick={onDownloadAss}>
          현재 구간 ASS 템플릿 생성
        </button>
        <button type="button" className="button ghost" disabled={assBusy} onClick={onSaveEditedAss}>
          {assBusy ? "ASS 저장 중…" : "ASS 원문 저장"}
        </button>
      </div>
      <p className="muted tiny">현재 텍스트 박스는 임시 편집본이고, 렌더에서 재사용하려면 반드시 저장을 눌러야 합니다.</p>
      <textarea
        className="textarea"
        rows={16}
        value={assText}
        onChange={(e) => onAssTextChange(e.target.value)}
        placeholder="여기에 raw ASS를 붙여 넣거나 템플릿을 만든 뒤 편집하세요."
      />
      {assMsg ? <p className="muted tiny">{assMsg}</p> : null}
    </div>
  );
}
