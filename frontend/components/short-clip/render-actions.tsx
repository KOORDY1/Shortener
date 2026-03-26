"use client";

type Props = {
  busyAction: "preview" | "final" | null;
  onPreview: () => void;
  onFinal: () => void;
};

export function RenderActions({ busyAction, onPreview, onFinal }: Props) {
  return (
    <div className="row wrap">
      <button type="button" className="button ghost" disabled={busyAction !== null} onClick={onPreview}>
        {busyAction === "preview" ? "Preview 생성 중…" : "FFmpeg preview clip 생성"}
      </button>
      <button type="button" className="button primary" disabled={busyAction !== null} onClick={onFinal}>
        {busyAction === "final" ? "최종 렌더 큐 등록 중…" : "최종 쇼츠 렌더"}
      </button>
    </div>
  );
}
