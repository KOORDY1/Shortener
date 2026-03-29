"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { apiBaseUrl } from "@/lib/api";
import { AssEditor } from "@/components/short-clip/ass-editor";
import { OutputPresetControls } from "@/components/short-clip/output-preset-controls";
import { RenderActions } from "@/components/short-clip/render-actions";
import { SubtitleSourceSelector } from "@/components/short-clip/subtitle-source-selector";
import { TranscriptSubtitleEditor } from "@/components/short-clip/transcript-subtitle-editor";
import { TrimControls } from "@/components/short-clip/trim-controls";
import type {
  ShortClipRenderConfig,
  ShortClipSubtitleStyle,
  TranscriptSegment
} from "@/lib/types";
import { formatPreciseTimecode, parseTimecodeInput } from "@/lib/format";

type Props = {
  candidateId: string;
  trimStart: number;
  trimEnd: number;
  onTrimStartChange: (value: number) => void;
  onTrimEndChange: (value: number) => void;
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
  trimStart,
  trimEnd,
  onTrimStartChange,
  onTrimEndChange,
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
  const [trimStartInput, setTrimStartInput] = useState(() => formatPreciseTimecode(trimStart));
  const [trimEndInput, setTrimEndInput] = useState(() => formatPreciseTimecode(trimEnd));
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

  const clipCacheKey = encodeURIComponent(shortClipPath ?? "missing");
  const previewClipCacheKey = encodeURIComponent(previewClipPath ?? "missing");
  const clipSrc = `${apiBaseUrl}/candidates/${candidateId}/short-clip/video?v=${clipCacheKey}`;
  const previewClipSrc = `${apiBaseUrl}/candidates/${candidateId}/short-clip/preview/video?v=${previewClipCacheKey}`;

  useEffect(() => {
    setTrimStartInput(formatPreciseTimecode(trimStart));
  }, [trimStart]);

  useEffect(() => {
    setTrimEndInput(formatPreciseTimecode(trimEnd));
  }, [trimEnd]);

  const t0 = trimStart;
  const t1 = trimEnd;
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
        <TrimControls
          trimStartInput={trimStartInput}
          trimEndInput={trimEndInput}
          onTrimStartInputChange={(nextValue) => {
            setTrimStartInput(nextValue);
            const parsed = parseTimecodeInput(nextValue);
            if (parsed != null) {
              onTrimStartChange(parsed);
            }
          }}
          onTrimEndInputChange={(nextValue) => {
            setTrimEndInput(nextValue);
            const parsed = parseTimecodeInput(nextValue);
            if (parsed != null) {
              onTrimEndChange(parsed);
            }
          }}
        />

        <OutputPresetControls
          aspectRatio={aspectRatio}
          resolutionPreset={resolutionPreset}
          fitMode={fitMode}
          qualityPreset={qualityPreset}
          width={width}
          height={height}
          aspectRatioOptions={ASPECT_RATIO_OPTIONS}
          resolutionOptions={resolutionOptions}
          fitModeOptions={FIT_MODE_OPTIONS}
          qualityOptions={QUALITY_OPTIONS}
          onAspectRatioChange={setAspectRatio}
          onResolutionPresetChange={setResolutionPreset}
          onFitModeChange={setFitMode}
          onQualityPresetChange={setQualityPreset}
        />

        <SubtitleSourceSelector
          subtitleSource={subtitleSource}
          importMsg={importMsg}
          onSubtitleSourceChange={setSubtitleSource}
          onImportSubtitles={(fileList) => {
            void onImportSubtitles(fileList);
          }}
        />

        {subtitleSource === "edited-ass" ? (
          <AssEditor
            assBusy={assBusy}
            assMsg={assMsg}
            assText={assText}
            onAssTextChange={setAssText}
            onDownloadAss={() => {
              void downloadAss();
            }}
            onSaveEditedAss={() => {
              void saveEditedAss();
            }}
          />
        ) : null}

        {burnSubtitles && subtitleSource === "transcript" ? (
          <TranscriptSubtitleEditor
            trimStart={t0}
            trimEnd={t1}
            fontFamily={fontFamily}
            fontSize={fontSize}
            alignment={alignment}
            marginV={marginV}
            outline={outline}
            primaryColor={primaryColor}
            outlineColor={outlineColor}
            shadow={shadow}
            backgroundBox={backgroundBox}
            bold={bold}
            alignOptions={ALIGN_OPTIONS}
            visibleSegments={visibleSegments}
            cueEdits={cueEdits}
            onFontFamilyChange={setFontFamily}
            onFontSizeChange={setFontSize}
            onAlignmentChange={setAlignment}
            onMarginVChange={setMarginV}
            onOutlineChange={setOutline}
            onPrimaryColorChange={setPrimaryColor}
            onOutlineColorChange={setOutlineColor}
            onShadowChange={setShadow}
            onBackgroundBoxChange={setBackgroundBox}
            onBoldChange={setBold}
            onCueEditChange={(segmentId, text) =>
              setCueEdits((prev) => ({
                ...prev,
                [segmentId]: text
              }))
            }
            onDownloadAss={() => {
              void downloadAss();
            }}
          />
        ) : null}

        {error ? <p className="muted" style={{ color: "var(--danger, #c00)" }}>{error}</p> : null}
        <RenderActions
          busyAction={busyAction}
          onPreview={() => {
            void submitRender("preview");
          }}
          onFinal={() => {
            void submitRender("final");
          }}
        />
      </div>
    </div>
  );
}
