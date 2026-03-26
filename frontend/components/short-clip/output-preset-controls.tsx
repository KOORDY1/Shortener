"use client";

type Option<T extends string> = {
  value: T;
  label: string;
};

type Props = {
  aspectRatio: "9:16" | "1:1" | "16:9";
  resolutionPreset: string;
  fitMode: "cover" | "contain" | "pad-blur";
  qualityPreset: "draft" | "standard" | "high";
  width: number;
  height: number;
  aspectRatioOptions: Option<"9:16" | "1:1" | "16:9">[];
  resolutionOptions: Option<string>[];
  fitModeOptions: Option<"cover" | "contain" | "pad-blur">[];
  qualityOptions: Option<"draft" | "standard" | "high">[];
  onAspectRatioChange: (value: "9:16" | "1:1" | "16:9") => void;
  onResolutionPresetChange: (value: string) => void;
  onFitModeChange: (value: "cover" | "contain" | "pad-blur") => void;
  onQualityPresetChange: (value: "draft" | "standard" | "high") => void;
};

export function OutputPresetControls({
  aspectRatio,
  resolutionPreset,
  fitMode,
  qualityPreset,
  width,
  height,
  aspectRatioOptions,
  resolutionOptions,
  fitModeOptions,
  qualityOptions,
  onAspectRatioChange,
  onResolutionPresetChange,
  onFitModeChange,
  onQualityPresetChange
}: Props) {
  return (
    <div className="stack panel soft">
      <strong className="tiny">출력 프리셋</strong>
      <div className="row wrap">
        <label className="field inline">
          <span className="muted">비율</span>
          <select className="input" value={aspectRatio} onChange={(e) => onAspectRatioChange(e.target.value as "9:16" | "1:1" | "16:9")}>
            {aspectRatioOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label className="field inline">
          <span className="muted">해상도</span>
          <select className="input" value={resolutionPreset} onChange={(e) => onResolutionPresetChange(e.target.value)}>
            {resolutionOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label className="field inline">
          <span className="muted">크롭/핏</span>
          <select className="input" value={fitMode} onChange={(e) => onFitModeChange(e.target.value as "cover" | "contain" | "pad-blur")}>
            {fitModeOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label className="field inline">
          <span className="muted">품질</span>
          <select
            className="input"
            value={qualityPreset}
            onChange={(e) => onQualityPresetChange(e.target.value as "draft" | "standard" | "high")}
          >
            {qualityOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
      </div>
      <p className="muted tiny">
        현재 출력: {width} x {height}. preview clip은 같은 비율과 자막/크롭 규칙을 유지한 채 더 작은 크기로 생성됩니다.
      </p>
    </div>
  );
}
