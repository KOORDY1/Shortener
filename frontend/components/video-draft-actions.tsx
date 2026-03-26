"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { apiBaseUrl } from "@/lib/api";
import type { ExportDetail, VideoDraftDetail } from "@/lib/types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {})
    }
  });
  if (!response.ok) {
    throw new Error(`요청 실패 (${response.status})`);
  }
  return response.json() as Promise<T>;
}

type Props = {
  draft: VideoDraftDetail;
};

export function VideoDraftActions({ draft }: Props) {
  const router = useRouter();
  const [notes, setNotes] = useState(draft.operator_notes ?? "");
  const [rejectReason, setRejectReason] = useState("");
  const [exportPreset, setExportPreset] = useState("shorts_default");
  const [saving, setSaving] = useState(false);
  const [actionBusy, setActionBusy] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [lastExport, setLastExport] = useState<ExportDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  const isRejected = draft.status === "rejected";

  async function onSaveNotes(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await request(`/video-drafts/${draft.id}`, {
        method: "PATCH",
        body: JSON.stringify({ operator_notes: notes })
      });
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "저장 실패");
    } finally {
      setSaving(false);
    }
  }

  async function onRerender() {
    setActionBusy("rerender");
    setError(null);
    try {
      await request(`/video-drafts/${draft.id}/rerender`, { method: "POST", body: "{}" });
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "재렌더 실패");
    } finally {
      setActionBusy(null);
    }
  }

  async function onApprove() {
    setActionBusy("approve");
    setError(null);
    try {
      await request(`/video-drafts/${draft.id}/approve`, { method: "POST", body: "{}" });
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "승인 실패");
    } finally {
      setActionBusy(null);
    }
  }

  async function onReject() {
    setActionBusy("reject");
    setError(null);
    try {
      await request(`/video-drafts/${draft.id}/reject`, {
        method: "POST",
        body: JSON.stringify({ reason: rejectReason.trim() || null })
      });
      setRejectReason("");
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "거절 실패");
    } finally {
      setActionBusy(null);
    }
  }

  async function onExport() {
    setExporting(true);
    setError(null);
    try {
      const trigger = await request<{
        export_id?: string | null;
        status: string;
        message?: string | null;
      }>(`/video-drafts/${draft.id}/exports`, {
        method: "POST",
        body: JSON.stringify({
          export_preset: exportPreset,
          include_srt: true,
          include_script_txt: true,
          include_metadata_json: true
        })
      });
      if (trigger.export_id) {
        const detail = await request<ExportDetail>(`/exports/${trigger.export_id}`);
        setLastExport(detail);
      }
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "보내기 실패");
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className="stack">
      {error ? <p className="muted" style={{ color: "var(--danger, #c00)" }}>{error}</p> : null}
      <form onSubmit={onSaveNotes} className="stack">
        <div className="field">
          <label>운영 메모</label>
          <textarea
            className="textarea"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={4}
          />
        </div>
        <button className="button ghost" type="submit" disabled={saving}>
          {saving ? "저장 중…" : "메모 저장"}
        </button>
      </form>
      <div className="row wrap">
        <button
          className="button ghost"
          type="button"
          disabled={!!actionBusy || isRejected}
          onClick={onRerender}
        >
          {actionBusy === "rerender" ? "재렌더 중…" : "템플릿 재렌더"}
        </button>
        <button
          className="button ghost"
          type="button"
          disabled={!!actionBusy || draft.status === "approved"}
          onClick={onApprove}
        >
          {actionBusy === "approve" ? "처리 중…" : "승인"}
        </button>
      </div>
      <div className="stack">
        <div className="field">
          <label>거절 사유(선택)</label>
          <input
            className="input"
            value={rejectReason}
            onChange={(e) => setRejectReason(e.target.value)}
            placeholder="짧게 입력"
          />
        </div>
        <button
          className="button danger"
          type="button"
          disabled={!!actionBusy || isRejected}
          onClick={onReject}
        >
          {actionBusy === "reject" ? "처리 중…" : "거절"}
        </button>
      </div>
      <div className="stack">
        <label className="field">
          <span>Export preset</span>
          <select className="input" value={exportPreset} onChange={(e) => setExportPreset(e.target.value)}>
            <option value="shorts_default">shorts_default</option>
            <option value="review_lowres">review_lowres</option>
            <option value="archive_master">archive_master</option>
          </select>
        </label>
        <button className="button" type="button" disabled={exporting} onClick={onExport}>
          {exporting ? "보내는 중…" : "최종 export 만들기"}
        </button>
      </div>
      {lastExport ? (
        <div className="panel stack">
          <p className="muted tiny">보내기 ID: {lastExport.id}</p>
          <p className="muted tiny">상태: {lastExport.status}</p>
          {lastExport.export_video_path ? (
            <p className="muted tiny path">{lastExport.export_video_path}</p>
          ) : null}
          <Link href={`/exports/${lastExport.id}`} className="link-button">
            보내기 상세
          </Link>
        </div>
      ) : null}
      <Link href={`/candidates/${draft.candidate_id}`} className="link-button">
        후보로 돌아가기
      </Link>
    </div>
  );
}
