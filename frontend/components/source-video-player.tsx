"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { apiBaseUrl } from "@/lib/api";

type Props = {
  episodeId: string;
  segmentStart?: number;
  segmentEnd?: number;
  onSegmentStartChange?: (value: number) => void;
  onSegmentEndChange?: (value: number) => void;
  playFromTime?: number | null;
  autoplayNonce?: number;
  showSegmentEditor?: boolean;
  /** 설정 시 업로드 VTT 또는 에피소드 자막(SRT/WebVTT) 기반 WebVTT를 `<track>`으로 겹칩니다(원본 타임라인). */
  webvttPreviewCandidateId?: string;
};

export function SourceVideoPlayer({
  episodeId,
  segmentStart = 0,
  segmentEnd,
  onSegmentStartChange,
  onSegmentEndChange,
  playFromTime,
  autoplayNonce,
  showSegmentEditor = false,
  webvttPreviewCandidateId
}: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [startInput, setStartInput] = useState(() => String(segmentStart));
  const [endInput, setEndInput] = useState(() => String(segmentEnd != null ? segmentEnd : segmentStart + 60));
  const [duration, setDuration] = useState(0);

  const src = `${apiBaseUrl}/episodes/${episodeId}/source-video`;
  const bounded = segmentEnd != null || showSegmentEditor;
  const sourceKey = `${src}|${webvttPreviewCandidateId ?? ""}|${segmentStart}|${segmentEnd ?? ""}`;
  const [errorState, setErrorState] = useState<{ key: string; message: string | null }>(() => ({
    key: sourceKey,
    message: null
  }));
  const error = errorState.key === sourceKey ? errorState.message : null;

  useEffect(() => {
    setStartInput(String(segmentStart));
  }, [segmentStart]);

  useEffect(() => {
    setEndInput(String(segmentEnd != null ? segmentEnd : segmentStart + 60));
  }, [segmentEnd, segmentStart]);

  const buildVideoErrorMessage = useCallback(() => {
    const mediaError = videoRef.current?.error;
    switch (mediaError?.code) {
      case MediaError.MEDIA_ERR_ABORTED:
        return "영상 로딩이 중단되었습니다. 다시 재생해 보세요.";
      case MediaError.MEDIA_ERR_NETWORK:
        return "영상 전송 중 네트워크 오류가 발생했습니다. 잠시 후 다시 시도해 보세요.";
      case MediaError.MEDIA_ERR_DECODE:
        return "영상 디코딩에 실패했습니다. 브라우저가 이 코덱을 지원하지 않거나 파일이 손상되었을 수 있습니다.";
      case MediaError.MEDIA_ERR_SRC_NOT_SUPPORTED:
        return "브라우저가 이 영상 형식 또는 코덱을 지원하지 않습니다.";
      default:
        return "영상을 불러오지 못했습니다. 잠시 후 다시 시도해 보세요.";
    }
  }, []);

  const previewT0 = segmentStart;
  const previewT1 = segmentEnd ?? segmentStart + 1;
  const vttSrc =
    webvttPreviewCandidateId &&
    Number.isFinite(previewT0) &&
    Number.isFinite(previewT1) &&
    previewT1 > previewT0
      ? `${apiBaseUrl}/candidates/${webvttPreviewCandidateId}/subtitles/webvtt?trim_start=${previewT0}&trim_end=${previewT1}`
      : null;

  const clampPlayback = useCallback(() => {
    const v = videoRef.current;
    if (!v || !bounded) return;
    const start = segmentStart;
    const end = segmentEnd as number;
    if (v.currentTime < start) v.currentTime = start;
    if (v.currentTime >= end) {
      v.pause();
      v.currentTime = start;
    }
  }, [bounded, segmentStart, segmentEnd]);

  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    const onTimeUpdate = () => clampPlayback();
    v.addEventListener("timeupdate", onTimeUpdate);
    return () => v.removeEventListener("timeupdate", onTimeUpdate);
  }, [clampPlayback]);

  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    const onMeta = () => {
      const d = v.duration;
      if (Number.isFinite(d)) setDuration(d);
      setErrorState({ key: sourceKey, message: null });
    };
    const onCanPlay = () => setErrorState({ key: sourceKey, message: null });
    const onPlaying = () => setErrorState({ key: sourceKey, message: null });
    const onErr = () => setErrorState({ key: sourceKey, message: buildVideoErrorMessage() });
    v.addEventListener("loadedmetadata", onMeta);
    v.addEventListener("canplay", onCanPlay);
    v.addEventListener("playing", onPlaying);
    v.addEventListener("error", onErr);
    return () => {
      v.removeEventListener("loadedmetadata", onMeta);
      v.removeEventListener("canplay", onCanPlay);
      v.removeEventListener("playing", onPlaying);
      v.removeEventListener("error", onErr);
    };
  }, [buildVideoErrorMessage, sourceKey, src]);

  useEffect(() => {
    if (playFromTime == null) return;
    const video = videoRef.current;
    if (!video) return;
    video.currentTime = playFromTime;
    void video.play().catch(() => undefined);
  }, [playFromTime, autoplayNonce]);

  function onPlay() {
    const v = videoRef.current;
    if (!v || !bounded) return;
    const start = segmentStart;
    const end = segmentEnd as number;
    if (v.currentTime < start || v.currentTime >= end) v.currentTime = start;
  }

  return (
    <div className="stack">
      <video
        key={src}
        ref={videoRef}
        className="source-video"
        controls
        preload="metadata"
        src={src}
        onPlay={onPlay}
        crossOrigin={vttSrc ? "anonymous" : undefined}
      >
        {vttSrc ? (
          <track
            key={vttSrc}
            kind="subtitles"
            src={vttSrc}
            srcLang="ko"
            label="자막 미리보기"
            default
          />
        ) : null}
      </video>
      {error ? <p className="muted" style={{ color: "var(--danger, #c00)" }}>{error}</p> : null}
      {showSegmentEditor ? (
        <div className="panel soft">
          <p className="muted tiny">
            재인코딩 없이 화면에서만 구간을 바꿔 미리봅니다. 실제 쇼츠 파일은 아래 「쇼츠 클립」에서 FFmpeg으로
            만듭니다.
          </p>
          <div className="row wrap">
            <label className="field inline">
              <span className="muted">시작(초)</span>
              <input
                className="input narrow"
                type="number"
                step={0.1}
                min={0}
                max={duration || undefined}
                value={startInput}
                onChange={(e) => {
                  const nextValue = e.target.value;
                  setStartInput(nextValue);
                  const parsed = Number.parseFloat(nextValue);
                  if (Number.isFinite(parsed)) {
                    onSegmentStartChange?.(parsed);
                  }
                }}
              />
            </label>
            <label className="field inline">
              <span className="muted">끝(초)</span>
              <input
                className="input narrow"
                type="number"
                step={0.1}
                min={segmentStart}
                max={duration || undefined}
                value={endInput}
                onChange={(e) => {
                  const nextValue = e.target.value;
                  setEndInput(nextValue);
                  const parsed = Number.parseFloat(nextValue);
                  if (Number.isFinite(parsed)) {
                    onSegmentEndChange?.(parsed);
                  }
                }}
              />
            </label>
            <button
              type="button"
              className="button ghost"
              onClick={() => {
                const v = videoRef.current;
                if (v) {
                  v.currentTime = segmentStart;
                  void v.play();
                }
              }}
            >
              이 구간부터 재생
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
