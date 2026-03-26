"use client";

import { useState } from "react";
import Link from "next/link";
import { CandidateJobsAndDraftsLive } from "@/components/candidate-jobs-and-drafts-live";
import { ShortClipPanel } from "@/components/short-clip-panel";
import { SourceVideoPlayer } from "@/components/source-video-player";
import { CandidateGenerateScriptsButton } from "@/components/mutation-buttons";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { formatDuration, formatTimecode } from "@/lib/format";
import { scoreKeyLabel } from "@/lib/labels";
import type {
  CandidateDetail,
  Job,
  ScriptDraft,
  ShortClipRenderConfig,
  VideoDraftSummary
} from "@/lib/types";

type Props = {
  candidateId: string;
  candidate: CandidateDetail;
  drafts: ScriptDraft[];
  jobs: Job[];
  videoDrafts: VideoDraftSummary[];
};

export function CandidateDetailContent({
  candidateId,
  candidate,
  drafts,
  jobs,
  videoDrafts
}: Props) {
  const generatedBy =
    typeof candidate.metadata.generated_by === "string"
      ? candidate.metadata.generated_by
      : null;
  const visionReason =
    typeof candidate.metadata.vision_reason === "string"
      ? candidate.metadata.vision_reason
      : null;
  const llmNote =
    typeof candidate.metadata.llm_note === "string"
      ? candidate.metadata.llm_note
      : null;
  const visionModel =
    typeof candidate.metadata.vision_model === "string"
      ? candidate.metadata.vision_model
      : null;
  const visionPromptVersion =
    typeof candidate.metadata.vision_prompt_version === "string"
      ? candidate.metadata.vision_prompt_version
      : null;
  const renderConfig: Partial<ShortClipRenderConfig> = candidate.render_config ?? {};
  const initialTrimStart =
    typeof renderConfig.trim_start === "number" ? renderConfig.trim_start : candidate.start_time;
  const initialTrimEnd =
    typeof renderConfig.trim_end === "number" ? renderConfig.trim_end : candidate.end_time;
  const [trimStartSec, setTrimStartSec] = useState(initialTrimStart);
  const [trimEndSec, setTrimEndSec] = useState(initialTrimEnd);

  return (
    <main className="page">
      <PageHeader
        title={`후보 #${candidateId.slice(0, 8)}`}
        subtitle={candidate.title_hint}
        backHref={`/episodes/${candidate.episode_id}/candidates`}
        actions={
          <>
            <CandidateGenerateScriptsButton candidateId={candidateId} />
            <Link href={`/episodes/${candidate.episode_id}`} className="link-button">
              에피소드
            </Link>
          </>
        }
      />

      <div className="panel">
        <h2 className="section-title">원본에서 이 구간 재생</h2>
        <SourceVideoPlayer
          episodeId={candidate.episode_id}
          segmentStart={trimStartSec}
          segmentEnd={trimEndSec}
          onSegmentStartChange={setTrimStartSec}
          onSegmentEndChange={setTrimEndSec}
          showSegmentEditor
          webvttPreviewCandidateId={candidateId}
        />
      </div>

      <ShortClipPanel
        candidateId={candidateId}
        trimStart={trimStartSec}
        trimEnd={trimEndSec}
        onTrimStartChange={setTrimStartSec}
        onTrimEndChange={setTrimEndSec}
        shortClipPath={candidate.short_clip_path}
        shortClipError={candidate.short_clip_error}
        previewClipPath={candidate.preview_clip_path}
        previewClipError={candidate.preview_clip_error}
        initialRenderConfig={candidate.render_config}
        hasEditedAss={candidate.has_edited_ass}
        transcriptSegments={candidate.transcript_segments}
      />

      <div className="grid three">
        <div className="kpi">
          <span className="muted">구간</span>
          <strong>
            {formatTimecode(candidate.start_time)} - {formatTimecode(candidate.end_time)}
          </strong>
        </div>
        <div className="kpi">
          <span className="muted">길이</span>
          <strong>{formatDuration(candidate.duration_seconds)}</strong>
        </div>
        <div className="kpi">
          <span className="muted">총점</span>
          <strong>{candidate.scores.total_score ?? "-"}</strong>
        </div>
        <div className="kpi">
          <span className="muted">후보 형태</span>
          <strong>{candidate.composite ? "Composite" : "Single span"}</strong>
        </div>
      </div>

      {(candidate.clip_spans ?? []).length > 0 ? (
        <div className="panel">
          <h2 className="section-title">클립 span</h2>
          <div className="stack">
            {(candidate.clip_spans ?? []).map((span, index) => (
              <div key={`${span.order}-${index}`} className="timeline-block">
                <strong>
                  #{index + 1} {formatTimecode(span.start_time)} - {formatTimecode(span.end_time)}
                </strong>
                <div>{span.role ?? (index === candidate.primary_span_index ? "primary" : "span")}</div>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      <div className="panel">
        <div className="row">
          <StatusBadge value={candidate.status} />
          <StatusBadge value={candidate.type} />
        </div>
      </div>

      {visionReason || llmNote || generatedBy ? (
        <div className="panel">
          <h2 className="section-title">추천 근거</h2>
          {visionReason ? <p>{visionReason}</p> : null}
          {llmNote ? <p className="muted">{llmNote}</p> : null}
          <div className="grid three">
            {generatedBy ? (
              <div className="kpi">
                <span className="muted">생성 경로</span>
                <strong>{generatedBy}</strong>
              </div>
            ) : null}
            {visionModel ? (
              <div className="kpi">
                <span className="muted">비전 모델</span>
                <strong>{visionModel}</strong>
              </div>
            ) : null}
            {visionPromptVersion ? (
              <div className="kpi">
                <span className="muted">프롬프트 버전</span>
                <strong>{visionPromptVersion}</strong>
              </div>
            ) : null}
          </div>
        </div>
      ) : null}

      <div className="panel">
        <h2 className="section-title">점수 항목</h2>
        <div className="grid three">
          {Object.entries(candidate.scores).map(([key, value]) => (
            <div key={key} className="kpi">
              <span className="muted">{scoreKeyLabel(key)}</span>
              <strong>{value}</strong>
            </div>
          ))}
        </div>
      </div>

      <div className="panel">
        <h2 className="section-title">구간 안의 샷</h2>
        <div className="shot-strip">
          {candidate.shots.map((shot) => (
            <div key={shot.id} className="shot-tile">
              <div className="thumbnail small">#{shot.shot_index}</div>
              <div className="muted tiny">
                {formatTimecode(shot.start_time)} – {formatTimecode(shot.end_time)}
              </div>
              {shot.thumbnail_path ? <div className="muted tiny path">{shot.thumbnail_path}</div> : null}
            </div>
          ))}
        </div>
        {candidate.shots.length === 0 ? <p className="muted">이 구간과 겹치는 샷이 없습니다.</p> : null}
      </div>

      {(candidate.transcript_segments ?? []).length > 0 ? (
        <div className="panel">
          <h2 className="section-title">에피소드 자막 구간</h2>
          <p className="muted tiny">
            새 업로드 시 넣은 SRT/WebVTT(또는 분석 파이프라인이 채운 대본)입니다. 없으면 이 블록은 숨겨집니다.
            쇼츠 패널에서 따로 가져온 VTT는 원본 플레이어 자막 트랙으로 우선 표시됩니다.
          </p>
          <div className="stack">
            {(candidate.transcript_segments ?? []).map((segment) => (
              <div key={segment.id} className="timeline-block">
                <strong>
                  {formatTimecode(segment.start_time)} - {formatTimecode(segment.end_time)}
                </strong>
                <div>{segment.text}</div>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      <CandidateJobsAndDraftsLive
        candidateId={candidateId}
        initialJobs={jobs}
        initialDrafts={drafts}
        initialVideoDrafts={videoDrafts}
      />
    </main>
  );
}
