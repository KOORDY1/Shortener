"use client";

import { formatTimecode } from "@/lib/format";
import type { TranscriptSegment } from "@/lib/types";

type Props = {
  trimStart: number;
  trimEnd: number;
  fontFamily: string;
  fontSize: number;
  alignment: number;
  marginV: number;
  outline: number;
  primaryColor: string;
  outlineColor: string;
  shadow: number;
  backgroundBox: boolean;
  bold: boolean;
  alignOptions: { value: number; label: string }[];
  visibleSegments: TranscriptSegment[];
  cueEdits: Record<string, string>;
  onFontFamilyChange: (value: string) => void;
  onFontSizeChange: (value: number) => void;
  onAlignmentChange: (value: number) => void;
  onMarginVChange: (value: number) => void;
  onOutlineChange: (value: number) => void;
  onPrimaryColorChange: (value: string) => void;
  onOutlineColorChange: (value: string) => void;
  onShadowChange: (value: number) => void;
  onBackgroundBoxChange: (value: boolean) => void;
  onBoldChange: (value: boolean) => void;
  onCueEditChange: (segmentId: string, text: string) => void;
  onCueEditSave: (segmentId: string, text: string) => void;
  onDownloadAss: () => void;
};

export function TranscriptSubtitleEditor({
  trimStart,
  trimEnd,
  fontFamily,
  fontSize,
  alignment,
  marginV,
  outline,
  primaryColor,
  outlineColor,
  shadow,
  backgroundBox,
  bold,
  alignOptions,
  visibleSegments,
  cueEdits,
  onFontFamilyChange,
  onFontSizeChange,
  onAlignmentChange,
  onMarginVChange,
  onOutlineChange,
  onPrimaryColorChange,
  onOutlineColorChange,
  onShadowChange,
  onBackgroundBoxChange,
  onBoldChange,
  onCueEditChange,
  onCueEditSave,
  onDownloadAss
}: Props) {
  return (
    <>
      <div className="stack" style={{ marginTop: 12 }}>
        <p className="muted tiny">
          대본을 바탕으로 ASS 템플릿을 받아 에디터에서 고친 뒤, 다시 「영상 자막 파일」로 가져와도 됩니다.
        </p>
        <div className="row wrap">
          <button type="button" className="button ghost" onClick={onDownloadAss}>
            현재 구간 ASS보내기 (대본 기준)
          </button>
        </div>
      </div>

      <div className="stack panel soft">
        <strong className="tiny">자막 스타일 (ASS 생성용)</strong>
        <div className="row wrap">
          <label className="field inline">
            <span className="muted">폰트</span>
            <input className="input" value={fontFamily} onChange={(e) => onFontFamilyChange(e.target.value)} />
          </label>
          <label className="field inline">
            <span className="muted">글자 크기</span>
            <input
              className="input narrow"
              type="number"
              min={10}
              max={80}
              value={fontSize}
              onChange={(e) => onFontSizeChange(Number.parseInt(e.target.value, 10) || 28)}
            />
          </label>
          <label className="field inline">
            <span className="muted">위치</span>
            <select
              className="input"
              value={alignment}
              onChange={(e) => onAlignmentChange(Number.parseInt(e.target.value, 10))}
            >
              {alignOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label className="field inline">
            <span className="muted">상하 여백</span>
            <input
              className="input narrow"
              type="number"
              min={0}
              max={400}
              value={marginV}
              onChange={(e) => onMarginVChange(Number.parseInt(e.target.value, 10) || 0)}
            />
          </label>
          <label className="field inline">
            <span className="muted">외곽선</span>
            <input
              className="input narrow"
              type="number"
              min={0}
              max={8}
              value={outline}
              onChange={(e) => onOutlineChange(Number.parseInt(e.target.value, 10) || 0)}
            />
          </label>
          <label className="field inline">
            <span className="muted">글자색</span>
            <input
              className="input narrow"
              type="color"
              value={primaryColor}
              onChange={(e) => onPrimaryColorChange(e.target.value)}
            />
          </label>
          <label className="field inline">
            <span className="muted">외곽선 색</span>
            <input
              className="input narrow"
              type="color"
              value={outlineColor}
              onChange={(e) => onOutlineColorChange(e.target.value)}
            />
          </label>
          <label className="field inline">
            <span className="muted">그림자</span>
            <input
              className="input narrow"
              type="number"
              min={0}
              max={8}
              value={shadow}
              onChange={(e) => onShadowChange(Number.parseInt(e.target.value, 10) || 0)}
            />
          </label>
          <label className="field inline row">
            <input type="checkbox" checked={bold} onChange={(e) => onBoldChange(e.target.checked)} />
            <span className="muted">굵게</span>
          </label>
          <label className="field inline row">
            <input
              type="checkbox"
              checked={backgroundBox}
              onChange={(e) => onBackgroundBoxChange(e.target.checked)}
            />
            <span className="muted">배경 박스</span>
          </label>
        </div>
      </div>

      {visibleSegments.length > 0 ? (
        <div className="stack">
          <strong className="tiny">
            자막 문구 편집 (구간 [{formatTimecode(trimStart)} – {formatTimecode(trimEnd)}]과 겹치는 큐)
          </strong>
          <div className="stack" style={{ maxHeight: 280, overflowY: "auto", gap: 10 }}>
            {visibleSegments.map((segment) => (
              <div key={segment.id} className="panel soft">
                <div className="muted tiny">
                  {formatTimecode(segment.start_time)} – {formatTimecode(segment.end_time)}
                </div>
                <textarea
                  className="textarea"
                  rows={2}
                  value={cueEdits[segment.id] ?? segment.text}
                  onChange={(e) => onCueEditChange(segment.id, e.target.value)}
                  onBlur={(e) => {
                    const newText = e.target.value;
                    if (newText !== segment.text) {
                      onCueEditSave(segment.id, newText);
                    }
                  }}
                />
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </>
  );
}
