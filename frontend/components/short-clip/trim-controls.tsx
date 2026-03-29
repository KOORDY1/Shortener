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
        <span className="muted">시작(MM:SS.SSS)</span>
        <input
          className="input narrow"
          type="text"
          value={trimStartInput}
          onChange={(e) => onTrimStartInputChange(e.target.value)}
        />
      </label>
      <label className="field inline">
        <span className="muted">끝(MM:SS.SSS)</span>
        <input
          className="input narrow"
          type="text"
          value={trimEndInput}
          onChange={(e) => onTrimEndInputChange(e.target.value)}
        />
      </label>
    </div>
  );
}
