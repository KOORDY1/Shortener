"use client";

type Props = {
  trimStartInput: string;
  trimEndInput: string;
  onTrimStartInputChange: (value: string) => void;
  onTrimEndInputChange: (value: string) => void;
};

export function TrimControls({
  trimStartInput,
  trimEndInput,
  onTrimStartInputChange,
  onTrimEndInputChange
}: Props) {
  return (
    <div className="row wrap">
      <label className="field inline">
        <span className="muted">시작(초)</span>
        <input
          className="input narrow"
          type="number"
          step={0.1}
          value={trimStartInput}
          onChange={(e) => onTrimStartInputChange(e.target.value)}
        />
      </label>
      <label className="field inline">
        <span className="muted">끝(초)</span>
        <input
          className="input narrow"
          type="number"
          step={0.1}
          value={trimEndInput}
          onChange={(e) => onTrimEndInputChange(e.target.value)}
        />
      </label>
    </div>
  );
}
