"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { apiBaseUrl } from "@/lib/api";
import type {
  ShortClipRenderConfig,
  ShortClipSubtitleStyle,
  TranscriptSegment
} from "@/lib/types";
import { formatTimecode } from "@/lib/format";

type Props = {
  candidateId: string;
  startTime: number;
  endTime: number;
  shortClipPath?: string | null;
  shortClipError?: string | null;
  previewClipPath?: string | null;
  previewClipError?: string | null;
  initialRenderConfig?: ShortClipRenderConfig;
  hasEditedAss?: boolean;
  transcriptSegments?: TranscriptSegment[];
};

function overlapsRange(seg: TranscriptSegment, clipStart: number, clipEnd: number) {
  return seg.start_time <= clipEnd && seg.end_time >= clipStart;
}

type SubtitleSource = "none" | "file" | "transcript" | "edited-ass";
type AspectRatioPreset = "9:16" | "1:1" | "16:9";
type FitMode = "cover" | "contain" | "pad-blur";
type QualityPreset = "draft" | "standard" | "high";

const DEFAULT_STYLE: ShortClipSubtitleStyle = {
  font_family: "Noto Sans CJK KR",
  font_size: 28,
  alignment: 2,
  margin_v: 52,
  outline: 2,
  primary_color: "#FFFFFF",
  outline_color: "#000000",
  shadow: 0,
  background_box: false,
  bold: false
};

const ALIGN_OPTIONS: { value: number; label: string }[] = [
  { value: 1, label: "하단 왼쪽" },
  { value: 2, label: "하단 중앙" },
  { value: 3, label: "하단 오른쪽" },
  { value: 4, label: "중앙 왼쪽" },
  { value: 5, label: "정중앙" },
  { value: 6, label: "중앙 오른쪽" },
  { value: 7, label: "상단 왼쪽" },
  { value: 8, label: "상단 중앙" },
  { value: 9, label: "상단 오른쪽" }
];

const ASPECT_RATIO_OPTIONS: { value: AspectRatioPreset; label: string }[] = [
  { value: "9:16", label: "9:16 세로형" },
  { value: "1:1", label: "1:1 정사각형" },
  { value: "16:9", label: "16:9 가로형" }
];

const RESOLUTION_PRESETS: Record<AspectRatioPreset, { value: string; label: string }[]> = {
  "9:16": [
    { value: "1080x1920", label: "1080 x 1920" },
    { value: "720x1280", label: "720 x 1280" }
  ],
  "1:1": [
    { value: "1080x1080", label: "1080 x 1080" },
    { value: "720x720", label: "720 x 720" }
  ],
  "16:9": [
    { value: "1920x1080", label: "1920 x 1080" },
    { value: "1280x720", label: "1280 x 720" }
  ]
};

const FIT_MODE_OPTIONS: { value: FitMode; label: string }[] = [
  { value: "contain", label: "Contain + pad" },
  { value: "cover", label: "Cover + crop" },
  { value: "pad-blur", label: "Pad + blur" }
];

const QUALITY_OPTIONS: { value: QualityPreset; label: string }[] = [
  { value: "draft", label: "Draft" },
  { value: "standard", label: "Standard" },
  { value: "high", label: "High" }
];

function inferAspectRatio(value?: string | null): AspectRatioPreset {
  if (value === "1:1" || value === "16:9") return value;
  return "9:16";
}

function parseResolutionPreset(value: string): { width: number; height: number } {
  const [rawWidth, rawHeight] = value.split("x");
  const width = Number.parseInt(rawWidth ?? "", 10);
  const height = Number.parseInt(rawHeight ?? "", 10);
  if (!Number.isFinite(width) || !Number.isFinite(height)) {
    return { width: 1080, height: 1920 };
  }
  return { width, height };
}

function buildResolutionPreset(width?: number | null, height?: number | null) {
  if (typeof width === "number" && typeof height === "number" && width > 0 && height > 0) {
    return `${width}x${height}`;
  }
  return "1080x1920";
}

export function ShortClipPanel({
  candidateId,
  startTime,
  endTime,
  shortClipPath,
  shortClipError,
  previewClipPath,
  previewClipError,
  initialRenderConfig,
  hasEditedAss = false,
  transcriptSegments = []
}: Props) {
  const router = useRouter();
  const savedSubtitleSource = (initialRenderConfig?.subtitle_source ?? "file") as SubtitleSource;
  const initialStyle = initialRenderConfig?.subtitle_style ?? DEFAULT_STYLE;
  const [trimStart, setTrimStart] = useState(
    String(initialRenderConfig?.trim_start ?? startTime)
  );
  const [trimEnd, setTrimEnd] = useState(String(initialRenderConfig?.trim_end ?? endTime));
  const [subtitleSource, setSubtitleSource] = useState<SubtitleSource>(savedSubtitleSource);
  const [aspectRatio, setAspectRatio] = useState<AspectRatioPreset>(
    inferAspectRatio(initialRenderConfig?.aspect_ratio)
  );
  const [resolutionPreset, setResolutionPreset] = useState(
    initialRenderConfig?.resolution_preset ??
      buildResolutionPreset(initialRenderConfig?.width, initialRenderConfig?.height)
  );
  const [fitMode, setFitMode] = useState<FitMode>(
    (initialRenderConfig?.fit_mode ?? "contain") as FitMode
  );
  const [qualityPreset, setQualityPreset] = useState<QualityPreset>(
    (initialRenderConfig?.quality_preset ?? "standard") as QualityPreset
  );
  const [fontFamily, setFontFamily] = useState(initialStyle.font_family);
  const [fontSize, setFontSize] = useState(initialStyle.font_size);
  const [alignment, setAlignment] = useState(initialStyle.alignment);
  const [marginV, setMarginV] = useState(initialStyle.margin_v);
  const [outline, setOutline] = useState(initialStyle.outline);
  const [primaryColor, setPrimaryColor] = useState(initialStyle.primary_color);
  const [outlineColor, setOutlineColor] = useState(initialStyle.outline_color);
  const [shadow, setShadow] = useState(initialStyle.shadow);
  const [backgroundBox, setBackgroundBox] = useState(initialStyle.background_box);
  const [bold, setBold] = useState(initialStyle.bold);
  const [cueEdits, setCueEdits] = useState<Record<string, string>>({});
  const [importMsg, setImportMsg] = useState<string | null>(null);
  const [assText, setAssText] = useState("");
  const [assLoaded, setAssLoaded] = useState(false);
  const [assBusy, setAssBusy] = useState(false);
  const [assMsg, setAssMsg] = useState<string | null>(null);

  const burnSubtitles = subtitleSource !== "none";
  const useImportedSubtitles = subtitleSource === "file";
  const useEditedAss = subtitleSource === "edited-ass";
  const [busyAction, setBusyAction] = useState<"preview" | "final" | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const next: Record<string, string> = {};
    for (const s of transcriptSegments) next[s.id] = s.text;
    for (const item of initialRenderConfig?.subtitle_text_overrides ?? []) {
      if (item?.segment_id) next[item.segment_id] = item.text;
    }
    setCueEdits(next);
  }, [initialRenderConfig?.subtitle_text_overrides, transcriptSegments]);

  useEffect(() => {
    const options = RESOLUTION_PRESETS[aspectRatio];
    const resolutionIsValid = options.some((option) => option.value === resolutionPreset);
    if (!resolutionIsValid) {
      setResolutionPreset(options[0].value);
    }
  }, [aspectRatio, resolutionPreset]);

  useEffect(() => {
    if ((!hasEditedAss && subtitleSource !== "edited-ass") || assLoaded) return;
    let ignore = false;
    async function loadEditedAss() {
      setAssBusy(true);
      try {
        const response = await fetch(`${apiBaseUrl}/candidates/${candidateId}/subtitles/edited-ass`, {
          cache: "no-store"
        });
        if (!response.ok) throw new Error(await response.text());
        const payload = (await response.json()) as { content?: string };
        if (!ignore) {
          setAssText(payload.content ?? "");
          setAssLoaded(true);
        }
      } catch (e) {
        if (!ignore) {
          setError(e instanceof Error ? e.message : "ASS 원문을 불러오지 못했습니다.");
        }
      } finally {
        if (!ignore) setAssBusy(false);
      }
    }
    void loadEditedAss();
    return () => {
      ignore = true;
    };
  }, [assLoaded, candidateId, hasEditedAss, subtitleSource]);

  const clipSrc = `${apiBaseUrl}/candidates/${candidateId}/short-clip/video`;
  const previewClipSrc = `${apiBaseUrl}/candidates/${candidateId}/short-clip/preview/video`;

  const t0 = parseFloat(trimStart);
  const t1 = parseFloat(trimEnd);
  const { width, height } = useMemo(() => parseResolutionPreset(resolutionPreset), [resolutionPreset]);
  const visibleSegments = useMemo(() => {
    if (!Number.isFinite(t0) || !Number.isFinite(t1) || t1 <= t0) return [];
    return (transcriptSegments ?? []).filter((s) => overlapsRange(s, t0, t1));
  }, [transcriptSegments, t0, t1]);
  const resolutionOptions = RESOLUTION_PRESETS[aspectRatio];

  async function downloadAss() {
    if (!Number.isFinite(t0) || !Number.isFinite(t1) || t1 <= t0) {
      setError("ASS보내기: 시작·끝 시각을 먼저 올바르게 입력하세요.");
      return;
    }
    setError(null);
    try {
      const u = new URL(`${apiBaseUrl}/candidates/${candidateId}/subtitles/ass`);
      u.searchParams.set("trim_start", String(t0));
      u.searchParams.set("trim_end", String(t1));
      u.searchParams.set("font_family", fontFamily);
      u.searchParams.set("font_size", String(fontSize));
      u.searchParams.set("alignment", String(alignment));
      u.searchParams.set("margin_v", String(marginV));
      u.searchParams.set("outline", String(outline));
      u.searchParams.set("primary_color", primaryColor);
      u.searchParams.set("outline_color", outlineColor);
      u.searchParams.set("shadow", String(shadow));
      u.searchParams.set("background_box", String(backgroundBox));
      u.searchParams.set("bold", String(bold));
      const r = await fetch(u.toString());
      if (!r.ok) throw new Error(await r.text());
      const blob = await r.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `clip_subs_${candidateId.slice(0, 8)}.ass`;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e) {
      setError(e instanceof Error ? e.message : "ASS 저장 실패");
    }
  }

  async function saveEditedAss() {
    setAssBusy(true);
    setAssMsg(null);
    setError(null);
    try {
      const response = await fetch(`${apiBaseUrl}/candidates/${candidateId}/subtitles/edited-ass`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: assText })
      });
      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || `실패 (${response.status})`);
      }
      setAssLoaded(true);
      setAssMsg(assText.trim() ? "ASS 원문을 저장했습니다." : "ASS 원문을 비웠습니다.");
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "ASS 저장 실패");
    } finally {
      setAssBusy(false);
    }
  }

  async function onImportSubtitles(fileList: FileList | null) {
    setImportMsg(null);
    setError(null);
    const f = fileList?.[0];
    if (!f) return;
    const fd = new FormData();
    fd.append("file", f);
    try {
      const r = await fetch(`${apiBaseUrl}/candidates/${candidateId}/subtitles/import`, {
        method: "POST",
        body: fd
      });
      const text = await r.text();
      if (!r.ok) throw new Error(text || `실패 (${r.status})`);
      setImportMsg("저장됨. 「영상 자막 파일」이 켜져 있으면 렌더 시 이 파일이 번인됩니다.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "가져오기 실패");
    }
  }

  async function submitRender(outputKind: "preview" | "final") {
    setBusyAction(outputKind);
    setError(null);
    try {
      if (!Number.isFinite(t0) || !Number.isFinite(t1) || t1 <= t0) {
        throw new Error("시작·끝 시각(초)을 올바르게 입력하세요.");
      }
      if (useEditedAss && !assText.trim()) {
        throw new Error("ASS 원문 모드에서는 ASS 내용을 먼저 입력하거나 저장하세요.");
      }
      const subtitle_text_overrides: { segment_id: string; text: string }[] = [];
      const segs = transcriptSegments ?? [];
      for (const s of segs) {
        const edited = cueEdits[s.id];
        if (edited !== undefined && edited !== s.text) {
          subtitle_text_overrides.push({ segment_id: s.id, text: edited });
        }
      }
      const body: Record<string, unknown> = {
        output_kind: outputKind,
        save_config: true,
        trim_start: t0,
        trim_end: t1,
        burn_subtitles: burnSubtitles,
        subtitle_source: subtitleSource,
        aspect_ratio: aspectRatio,
        fit_mode: fitMode,
        quality_preset: qualityPreset,
        resolution_preset: resolutionPreset,
        width,
        height
      };
      if (burnSubtitles) {
        body.use_imported_subtitles = useImportedSubtitles;
        body.use_edited_ass = useEditedAss;
        if (useEditedAss) {
          body.edited_ass = assText;
        } else if (!useImportedSubtitles) {
          body.subtitle_style = {
            font_family: fontFamily,
            font_size: fontSize,
            alignment,
            margin_v: marginV,
            outline,
            primary_color: primaryColor,
            outline_color: outlineColor,
            shadow,
            background_box: backgroundBox,
            bold
          };
          if (subtitle_text_overrides.length > 0) {
            body.subtitle_text_overrides = subtitle_text_overrides;
          }
        }
      }
      const response = await fetch(`${apiBaseUrl}/candidates/${candidateId}/short-clip`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
      });
      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || `요청 실패 (${response.status})`);
      }
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "오류");
    } finally {
      setBusyAction(null);
    }
  }

  return (
    <div className="panel stack">
      <h2 className="section-title">렌더 에디터 (FFmpeg 재인코딩·자막 번인)</h2>
      <p className="muted tiny">
        브라우저에서는 즉시 미리보고, 필요할 때 같은 설정으로 FFmpeg preview clip을 따로 뽑아 최종 결과에
        가깝게 확인할 수 있습니다.
      </p>
      {shortClipError ? (
        <p className="muted" style={{ color: "var(--danger, #c00)" }}>
          마지막 렌더 오류: {shortClipError}
        </p>
      ) : null}
      {previewClipError ? (
        <p className="muted" style={{ color: "var(--danger, #c00)" }}>
          마지막 preview 오류: {previewClipError}
        </p>
      ) : null}
      {previewClipPath ? (
        <div className="stack">
          <p className="muted tiny">FFmpeg preview clip (저해상도, 같은 프리셋)</p>
          <video key={previewClipSrc} className="source-video" controls preload="metadata" src={previewClipSrc} />
        </div>
      ) : null}
      {shortClipPath ? (
        <div className="stack">
          <p className="muted tiny">최종 렌더 쇼츠 (설정 바꾼 뒤 다시 렌더하면 덮어씁니다)</p>
          <video key={clipSrc} className="source-video" controls preload="metadata" src={clipSrc} />
        </div>
      ) : (
        <p className="muted tiny">아직 렌더된 클립이 없습니다. 아래에서 실행하세요.</p>
      )}
      <div className="stack panel soft">
        <div className="row wrap">
          <label className="field inline">
            <span className="muted">시작(초)</span>
            <input
              className="input narrow"
              type="number"
              step={0.1}
              value={trimStart}
              onChange={(e) => setTrimStart(e.target.value)}
            />
          </label>
          <label className="field inline">
            <span className="muted">끝(초)</span>
            <input
              className="input narrow"
              type="number"
              step={0.1}
              value={trimEnd}
              onChange={(e) => setTrimEnd(e.target.value)}
            />
          </label>
        </div>

        <div className="stack panel soft">
          <strong className="tiny">출력 프리셋</strong>
          <div className="row wrap">
            <label className="field inline">
              <span className="muted">비율</span>
              <select className="input" value={aspectRatio} onChange={(e) => setAspectRatio(e.target.value as AspectRatioPreset)}>
                {ASPECT_RATIO_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="field inline">
              <span className="muted">해상도</span>
              <select className="input" value={resolutionPreset} onChange={(e) => setResolutionPreset(e.target.value)}>
                {resolutionOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="field inline">
              <span className="muted">크롭/핏</span>
              <select className="input" value={fitMode} onChange={(e) => setFitMode(e.target.value as FitMode)}>
                {FIT_MODE_OPTIONS.map((option) => (
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
                onChange={(e) => setQualityPreset(e.target.value as QualityPreset)}
              >
                {QUALITY_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <p className="muted tiny">
            현재 출력: {width} x {height}. preview clip은 같은 비율과 자막/크롭 규칙을 유지한 채 더 작은 크기로
            생성됩니다.
          </p>
        </div>

        <div className="stack panel soft">
          <strong className="tiny">화면 자막 (영상에 번인)</strong>
          <p className="muted tiny">
            원하시는 방식 하나만 선택하세요. 스크립트 초안·음성 대본은 이 설정과 별개입니다.
          </p>
          <div className="stack" style={{ gap: 10 }}>
            <label className="field row" style={{ alignItems: "flex-start", gap: 8 }}>
              <input
                type="radio"
                name="subtitleSource"
                checked={subtitleSource === "file"}
                onChange={() => setSubtitleSource("file")}
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
                onChange={() => setSubtitleSource("transcript")}
              />
              <span>
                <strong>에피소드 자막에서 자동</strong>
                <span className="muted tiny" style={{ display: "block" }}>
                  새 업로드 시 함께 넣은 SRT/WebVTT를 구간에 맞게 SRT로 만들어 번인합니다. 없으면 자막이 비어
                  있습니다. 아래에서 스타일·문구를 고칠 수 있습니다.
                </span>
              </span>
            </label>
            <label className="field row" style={{ alignItems: "flex-start", gap: 8 }}>
              <input
                type="radio"
                name="subtitleSource"
                checked={subtitleSource === "edited-ass"}
                onChange={() => setSubtitleSource("edited-ass")}
              />
              <span>
                <strong>ASS 원문 직접 편집</strong>
                <span className="muted tiny" style={{ display: "block" }}>
                  후보 단위로 저장한 raw ASS를 그대로 렌더합니다. 브라우저 플레이어는 ASS를 직접 그리지 못하므로,
                  이 모드는 FFmpeg preview clip로 확인하는 편이 정확합니다.
                </span>
              </span>
            </label>
            <label className="field row" style={{ alignItems: "flex-start", gap: 8 }}>
              <input
                type="radio"
                name="subtitleSource"
                checked={subtitleSource === "none"}
                onChange={() => setSubtitleSource("none")}
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
                    onChange={(e) => void onImportSubtitles(e.target.files)}
                  />
                </label>
              </div>
              {importMsg ? <p className="muted tiny">{importMsg}</p> : null}
              <p className="muted tiny">
                원본 플레이어 자막: 쇼츠용으로 가져온 .vtt가 있으면 그걸 쓰고, 없으면 에피소드 자막(원본
                타임코드)입니다. ASS만 올린 경우 브라우저 트랙은 VTT를 따로 올리면 미리볼 수 있습니다.
              </p>
            </div>
          ) : null}

          {subtitleSource === "edited-ass" ? (
            <div className="stack" style={{ marginTop: 12 }}>
              <div className="row wrap">
                <button type="button" className="button ghost" onClick={() => void downloadAss()}>
                  현재 구간 ASS 템플릿 생성
                </button>
                <button type="button" className="button ghost" disabled={assBusy} onClick={() => void saveEditedAss()}>
                  {assBusy ? "ASS 저장 중…" : "ASS 원문 저장"}
                </button>
              </div>
              <textarea
                className="textarea"
                rows={16}
                value={assText}
                onChange={(e) => setAssText(e.target.value)}
                placeholder="여기에 raw ASS를 붙여 넣거나 템플릿을 만든 뒤 편집하세요."
              />
              {assMsg ? <p className="muted tiny">{assMsg}</p> : null}
            </div>
          ) : null}

          {subtitleSource === "transcript" ? (
            <div className="stack" style={{ marginTop: 12 }}>
              <p className="muted tiny">
                대본을 바탕으로 ASS 템플릿을 받아 에디터에서 고친 뒤, 다시 「영상 자막 파일」로 가져와도
                됩니다.
              </p>
              <div className="row wrap">
                <button type="button" className="button ghost" onClick={() => void downloadAss()}>
                  현재 구간 ASS보내기 (대본 기준)
                </button>
              </div>
            </div>
          ) : null}
        </div>

        {burnSubtitles && subtitleSource === "transcript" ? (
          <div className="stack panel soft">
            <strong className="tiny">자막 스타일 (ASS 생성용)</strong>
            <div className="row wrap">
              <label className="field inline">
                <span className="muted">폰트</span>
                <input className="input" value={fontFamily} onChange={(e) => setFontFamily(e.target.value)} />
              </label>
              <label className="field inline">
                <span className="muted">글자 크기</span>
                <input
                  className="input narrow"
                  type="number"
                  min={10}
                  max={80}
                  value={fontSize}
                  onChange={(e) => setFontSize(parseInt(e.target.value, 10) || 28)}
                />
              </label>
              <label className="field inline">
                <span className="muted">위치</span>
                <select
                  className="input"
                  value={alignment}
                  onChange={(e) => setAlignment(parseInt(e.target.value, 10))}
                >
                  {ALIGN_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
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
                  onChange={(e) => setMarginV(parseInt(e.target.value, 10) || 0)}
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
                  onChange={(e) => setOutline(parseInt(e.target.value, 10) || 0)}
                />
              </label>
              <label className="field inline">
                <span className="muted">글자색</span>
                <input
                  className="input narrow"
                  type="color"
                  value={primaryColor}
                  onChange={(e) => setPrimaryColor(e.target.value)}
                />
              </label>
              <label className="field inline">
                <span className="muted">외곽선 색</span>
                <input
                  className="input narrow"
                  type="color"
                  value={outlineColor}
                  onChange={(e) => setOutlineColor(e.target.value)}
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
                  onChange={(e) => setShadow(parseInt(e.target.value, 10) || 0)}
                />
              </label>
              <label className="field inline row">
                <input type="checkbox" checked={bold} onChange={(e) => setBold(e.target.checked)} />
                <span className="muted">굵게</span>
              </label>
              <label className="field inline row">
                <input
                  type="checkbox"
                  checked={backgroundBox}
                  onChange={(e) => setBackgroundBox(e.target.checked)}
                />
                <span className="muted">배경 박스</span>
              </label>
            </div>
          </div>
        ) : null}

        {burnSubtitles && subtitleSource === "transcript" && visibleSegments.length > 0 ? (
          <div className="stack">
            <strong className="tiny">
              자막 문구 편집 (구간 [{formatTimecode(t0)} – {formatTimecode(t1)}]과 겹치는 큐)
            </strong>
            <div className="stack" style={{ maxHeight: 280, overflowY: "auto", gap: 10 }}>
              {visibleSegments.map((s) => (
                <div key={s.id} className="panel soft">
                  <div className="muted tiny">
                    {formatTimecode(s.start_time)} – {formatTimecode(s.end_time)}
                  </div>
                  <textarea
                    className="textarea"
                    rows={2}
                    value={cueEdits[s.id] ?? s.text}
                    onChange={(e) =>
                      setCueEdits((prev) => ({
                        ...prev,
                        [s.id]: e.target.value
                      }))
                    }
                  />
                </div>
              ))}
            </div>
          </div>
        ) : null}

        {error ? <p className="muted" style={{ color: "var(--danger, #c00)" }}>{error}</p> : null}
        <div className="row wrap">
          <button
            type="button"
            className="button ghost"
            disabled={busyAction !== null}
            onClick={() => void submitRender("preview")}
          >
            {busyAction === "preview" ? "Preview 생성 중…" : "FFmpeg preview clip 생성"}
          </button>
          <button
            type="button"
            className="button primary"
            disabled={busyAction !== null}
            onClick={() => void submitRender("final")}
          >
            {busyAction === "final" ? "최종 렌더 큐 등록 중…" : "최종 쇼츠 렌더"}
          </button>
        </div>
      </div>
    </div>
  );
}
