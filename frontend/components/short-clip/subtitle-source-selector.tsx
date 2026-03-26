"use client";

type SubtitleSource = "none" | "file" | "transcript" | "edited-ass";

type Props = {
  subtitleSource: SubtitleSource;
  importMsg: string | null;
  onSubtitleSourceChange: (value: SubtitleSource) => void;
  onImportSubtitles: (fileList: FileList | null) => void;
};

export function SubtitleSourceSelector({
  subtitleSource,
  importMsg,
  onSubtitleSourceChange,
  onImportSubtitles
}: Props) {
  return (
    <div className="stack panel soft">
      <strong className="tiny">화면 자막 (영상에 번인)</strong>
      <p className="muted tiny">원하시는 방식 하나만 선택하세요. 스크립트 초안·음성 대본은 이 설정과 별개입니다.</p>
      <div className="stack" style={{ gap: 10 }}>
        <label className="field row" style={{ alignItems: "flex-start", gap: 8 }}>
          <input
            type="radio"
            name="subtitleSource"
            checked={subtitleSource === "file"}
            onChange={() => onSubtitleSourceChange("file")}
          />
          <span>
            <strong>영상 자막 파일</strong>
            <span className="muted tiny" style={{ display: "block" }}>
              Aegisub 등에서 만든 .ass 또는 .vtt를 올리면 그대로 번인합니다. 타임코드는{" "}
              <strong>이 클립 구간 시작이 0초</strong>인 파일이어야 맞습니다.
            </span>
          </span>
        </label>
        <label className="field row" style={{ alignItems: "flex-start", gap: 8 }}>
          <input
            type="radio"
            name="subtitleSource"
            checked={subtitleSource === "transcript"}
            onChange={() => onSubtitleSourceChange("transcript")}
          />
          <span>
            <strong>에피소드 자막에서 자동</strong>
            <span className="muted tiny" style={{ display: "block" }}>
              새 업로드 시 함께 넣은 SRT/WebVTT를 구간에 맞게 SRT로 만들어 번인합니다. 없으면 자막이 비어 있습니다.
              아래에서 스타일·문구를 고칠 수 있습니다.
            </span>
          </span>
        </label>
        <label className="field row" style={{ alignItems: "flex-start", gap: 8 }}>
          <input
            type="radio"
            name="subtitleSource"
            checked={subtitleSource === "edited-ass"}
            onChange={() => onSubtitleSourceChange("edited-ass")}
          />
          <span>
            <strong>ASS 원문 직접 편집</strong>
            <span className="muted tiny" style={{ display: "block" }}>
              후보 단위로 저장한 raw ASS를 그대로 렌더합니다. 브라우저 플레이어는 ASS를 직접 그리지 못하므로, 이 모드는
              FFmpeg preview clip로 확인하는 편이 정확합니다.
            </span>
          </span>
        </label>
        <label className="field row" style={{ alignItems: "flex-start", gap: 8 }}>
          <input
            type="radio"
            name="subtitleSource"
            checked={subtitleSource === "none"}
            onChange={() => onSubtitleSourceChange("none")}
          />
          <span>
            <strong>자막 없음</strong>
            <span className="muted tiny" style={{ display: "block" }}>
              말풍선·자막 없이 영상만 출력합니다.
            </span>
          </span>
        </label>
      </div>

      {subtitleSource === "file" ? (
        <div className="stack" style={{ marginTop: 12 }}>
          <div className="row wrap">
            <label className="field inline row">
              <span className="muted">가져오기 (.ass / .vtt)</span>
              <input
                type="file"
                accept=".ass,.vtt"
                className="input"
                onChange={(e) => onImportSubtitles(e.target.files)}
              />
            </label>
          </div>
          {importMsg ? <p className="muted tiny">{importMsg}</p> : null}
          <p className="muted tiny">
            원본 플레이어 자막: 쇼츠용으로 가져온 .vtt가 있으면 그걸 쓰고, 없으면 에피소드 자막(원본 타임코드)입니다.
            ASS만 올린 경우 브라우저 트랙은 VTT를 따로 올리면 미리볼 수 있습니다.
          </p>
        </div>
      ) : null}
    </div>
  );
}
