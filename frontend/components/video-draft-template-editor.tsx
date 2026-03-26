"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { apiBaseUrl } from "@/lib/api";
import type { VideoDraftDetail } from "@/lib/types";

type Props = {
  draft: VideoDraftDetail;
};

function deepClone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value));
}

export function VideoDraftTemplateEditor({ draft }: Props) {
  const router = useRouter();
  const initialConfig = useMemo(
    () => ({
      fit_mode: "contain",
      top_safe_area_height: 240,
      bottom_safe_area_height: 300,
      subtitle_source: draft.burned_caption ? "transcript" : "none",
      text_slots: {
        top_title: { text: "", font_size: 60, color: "#FFFFFF", align: "center", offset_x: 0, offset_y: 24 },
        bottom_caption: {
          text: "",
          font_size: 34,
          color: "#F8F8F8",
          align: "center",
          offset_x: 0,
          offset_y: -72
        },
        source_label: {
          text: "",
          font_size: 24,
          color: "#DDDDDD",
          align: "left",
          offset_x: 24,
          offset_y: -18
        }
      },
      intro_tts_enabled: false,
      intro_tts_text: "",
      intro_duration_sec: 2.4,
      outro_tts_enabled: false,
      outro_tts_text: "",
      outro_duration_sec: 2.2,
      tts_voice_key: draft.tts_voice_key ?? "ko_female_01",
      tts_volume: 1,
      duck_original_audio: false,
      ...(draft.render_config ?? {})
    }),
    [draft]
  );
  const [config, setConfig] = useState<Record<string, unknown>>(initialConfig);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function update(path: string[], value: unknown) {
    setConfig((prev) => {
      const next = deepClone(prev);
      let cursor: Record<string, unknown> = next;
      for (const key of path.slice(0, -1)) {
        const current = cursor[key];
        if (!current || typeof current !== "object") {
          cursor[key] = {};
        }
        cursor = cursor[key] as Record<string, unknown>;
      }
      cursor[path[path.length - 1]] = value;
      return next;
    });
  }

  async function saveConfig() {
    setSaving(true);
    setError(null);
    try {
      const response = await fetch(`${apiBaseUrl}/video-drafts/${draft.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ render_config: config })
      });
      if (!response.ok) {
        throw new Error(`저장 실패 (${response.status})`);
      }
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "저장 실패");
    } finally {
      setSaving(false);
    }
  }

  const slots = (config.text_slots as Record<string, Record<string, unknown>> | undefined) ?? {};
  const previewStyle = {
    width: 240,
    aspectRatio: "9 / 16",
    background: String(config.background_color ?? "#111111"),
    borderRadius: 16,
    overflow: "hidden" as const,
    border: "1px solid rgba(255,255,255,0.08)"
  };
  const topSafe = Number(config.top_safe_area_height ?? 240);
  const bottomSafe = Number(config.bottom_safe_area_height ?? 300);

  return (
    <div className="panel stack">
      <h2 className="section-title">템플릿 설정</h2>
      {error ? <p className="muted" style={{ color: "var(--danger, #c00)" }}>{error}</p> : null}
      <div className="panel soft stack">
        <strong>슬롯 미리보기</strong>
        <div style={previewStyle}>
          <div
            style={{
              height: `${Math.max(12, (topSafe / Number(draft.height || 1920)) * 100)}%`,
              padding: 12,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              textAlign: "center",
              color: String(slots.top_title?.color ?? "#FFFFFF"),
              fontSize: Math.max(12, Number(slots.top_title?.font_size ?? 60) / 4)
            }}
          >
            {String(slots.top_title?.text ?? "").trim() || "TOP TITLE"}
          </div>
          <div
            style={{
              flex: 1,
              minHeight: 180,
              background: "#222",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "#888"
            }}
          >
            content area
          </div>
          <div
            style={{
              height: `${Math.max(14, (bottomSafe / Number(draft.height || 1920)) * 100)}%`,
              padding: 12,
              display: "flex",
              flexDirection: "column" as const,
              justifyContent: "space-between",
              gap: 8
            }}
          >
            <div
              style={{
                textAlign: "center",
                color: String(slots.bottom_caption?.color ?? "#F8F8F8"),
                fontSize: Math.max(11, Number(slots.bottom_caption?.font_size ?? 34) / 4)
              }}
            >
              {String(slots.bottom_caption?.text ?? "").trim() || "BOTTOM CAPTION"}
            </div>
            <div
              style={{
                textAlign: "left",
                color: String(slots.source_label?.color ?? "#DDDDDD"),
                fontSize: Math.max(10, Number(slots.source_label?.font_size ?? 24) / 4)
              }}
            >
              {String(slots.source_label?.text ?? "").trim() || "SOURCE LABEL"}
            </div>
          </div>
        </div>
      </div>
      <div className="grid two">
        <label className="field">
          <span>핏 모드</span>
          <select
            className="input"
            value={String(config.fit_mode ?? "contain")}
            onChange={(e) => update(["fit_mode"], e.target.value)}
          >
            <option value="contain">Contain</option>
            <option value="cover">Cover</option>
            <option value="pad-blur">Pad Blur</option>
          </select>
        </label>
        <label className="field">
          <span>자막 소스</span>
          <select
            className="input"
            value={String(config.subtitle_source ?? "transcript")}
            onChange={(e) => update(["subtitle_source"], e.target.value)}
          >
            <option value="transcript">Transcript</option>
            <option value="file">Imported file</option>
            <option value="edited-ass">Edited ASS</option>
            <option value="none">None</option>
          </select>
        </label>
        <label className="field">
          <span>Top safe area</span>
          <input
            className="input"
            type="number"
            value={Number(config.top_safe_area_height ?? 240)}
            onChange={(e) => update(["top_safe_area_height"], Number(e.target.value))}
          />
        </label>
        <label className="field">
          <span>Bottom safe area</span>
          <input
            className="input"
            type="number"
            value={Number(config.bottom_safe_area_height ?? 300)}
            onChange={(e) => update(["bottom_safe_area_height"], Number(e.target.value))}
          />
        </label>
      </div>

      {["top_title", "bottom_caption", "source_label"].map((slotName) => {
        const slot = slots[slotName] ?? {};
        return (
          <div key={slotName} className="panel soft stack">
            <strong>{slotName}</strong>
            <label className="field">
              <span>텍스트</span>
              <input
                className="input"
                value={String(slot.text ?? "")}
                onChange={(e) => update(["text_slots", slotName, "text"], e.target.value)}
              />
            </label>
            <div className="grid two">
              <label className="field">
                <span>폰트 크기</span>
                <input
                  className="input"
                  type="number"
                  value={Number(slot.font_size ?? 36)}
                  onChange={(e) => update(["text_slots", slotName, "font_size"], Number(e.target.value))}
                />
              </label>
              <label className="field">
                <span>색상</span>
                <input
                  className="input"
                  type="color"
                  value={String(slot.color ?? "#FFFFFF")}
                  onChange={(e) => update(["text_slots", slotName, "color"], e.target.value)}
                />
              </label>
              <label className="field">
                <span>정렬</span>
                <select
                  className="input"
                  value={String(slot.align ?? "center")}
                  onChange={(e) => update(["text_slots", slotName, "align"], e.target.value)}
                >
                  <option value="left">left</option>
                  <option value="center">center</option>
                  <option value="right">right</option>
                </select>
              </label>
              <label className="field">
                <span>offset_x / offset_y</span>
                <div className="row">
                  <input
                    className="input"
                    type="number"
                    value={Number(slot.offset_x ?? 0)}
                    onChange={(e) => update(["text_slots", slotName, "offset_x"], Number(e.target.value))}
                  />
                  <input
                    className="input"
                    type="number"
                    value={Number(slot.offset_y ?? 0)}
                    onChange={(e) => update(["text_slots", slotName, "offset_y"], Number(e.target.value))}
                  />
                </div>
              </label>
            </div>
          </div>
        );
      })}

      <div className="panel soft stack">
        <strong>Intro / Outro TTS</strong>
        <div className="grid two">
          <label className="field row">
            <input
              type="checkbox"
              checked={Boolean(config.intro_tts_enabled)}
              onChange={(e) => update(["intro_tts_enabled"], e.target.checked)}
            />
            <span>Intro TTS 사용</span>
          </label>
          <label className="field row">
            <input
              type="checkbox"
              checked={Boolean(config.outro_tts_enabled)}
              onChange={(e) => update(["outro_tts_enabled"], e.target.checked)}
            />
            <span>Outro TTS 사용</span>
          </label>
          <label className="field">
            <span>Intro 텍스트</span>
            <input
              className="input"
              value={String(config.intro_tts_text ?? "")}
              onChange={(e) => update(["intro_tts_text"], e.target.value)}
            />
          </label>
          <label className="field">
            <span>Outro 텍스트</span>
            <input
              className="input"
              value={String(config.outro_tts_text ?? "")}
              onChange={(e) => update(["outro_tts_text"], e.target.value)}
            />
          </label>
          <label className="field">
            <span>Intro 길이(초)</span>
            <input
              className="input"
              type="number"
              step={0.1}
              value={Number(config.intro_duration_sec ?? 2.4)}
              onChange={(e) => update(["intro_duration_sec"], Number(e.target.value))}
            />
          </label>
          <label className="field">
            <span>Outro 길이(초)</span>
            <input
              className="input"
              type="number"
              step={0.1}
              value={Number(config.outro_duration_sec ?? 2.2)}
              onChange={(e) => update(["outro_duration_sec"], Number(e.target.value))}
            />
          </label>
          <label className="field">
            <span>TTS Voice</span>
            <input
              className="input"
              value={String(config.tts_voice_key ?? "ko_female_01")}
              onChange={(e) => update(["tts_voice_key"], e.target.value)}
            />
          </label>
          <label className="field">
            <span>TTS 볼륨</span>
            <input
              className="input"
              type="number"
              step={0.1}
              value={Number(config.tts_volume ?? 1)}
              onChange={(e) => update(["tts_volume"], Number(e.target.value))}
            />
          </label>
          <label className="field row">
            <input
              type="checkbox"
              checked={Boolean(config.duck_original_audio)}
              onChange={(e) => update(["duck_original_audio"], e.target.checked)}
            />
            <span>원본 오디오 감쇠</span>
          </label>
        </div>
      </div>

      <button className="button ghost" type="button" disabled={saving} onClick={() => void saveConfig()}>
        {saving ? "저장 중…" : "템플릿 설정 저장"}
      </button>
    </div>
  );
}
