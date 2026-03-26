export type Episode = {
  id: string;
  show_title: string;
  season_number?: number | null;
  episode_number?: number | null;
  episode_title?: string | null;
  original_language?: string;
  target_channel: string;
  status: string;
  source_video_path?: string;
  source_subtitle_path?: string | null;
  proxy_video_path?: string | null;
  audio_path?: string | null;
  duration_seconds?: number | null;
  fps?: number | null;
  width?: number | null;
  height?: number | null;
  metadata?: Record<string, unknown>;
  created_at?: string | null;
};

export type EpisodeListResponse = {
  items: Episode[];
  page: number;
  page_size: number;
  total: number;
};

export type EpisodeOperationOkResponse = {
  ok: boolean;
  message: string;
};

export type Job = {
  id: string;
  episode_id?: string | null;
  candidate_id?: string | null;
  type: string;
  status: string;
  progress_percent: number;
  current_step?: string | null;
  error_message?: string | null;
  payload: Record<string, unknown>;
  created_at?: string | null;
  updated_at?: string | null;
};

export type JobListResponse = {
  items: Job[];
  total: number;
};

export type CandidateSummary = {
  id: string;
  candidate_index: number;
  type: string;
  status: string;
  title_hint: string;
  start_time: number;
  end_time: number;
  duration_seconds: number;
  total_score: number;
  composite?: boolean;
  span_count?: number;
};

export type ClipSpan = {
  start_time: number;
  end_time: number;
  order: number;
  role?: string | null;
};

export type CandidateListResponse = {
  items: CandidateSummary[];
  total: number;
};

export type TranscriptSegment = {
  id: string;
  start_time: number;
  end_time: number;
  text: string;
  speaker_label?: string | null;
};

export type Shot = {
  id: string;
  shot_index: number;
  start_time: number;
  end_time: number;
  thumbnail_path?: string | null;
};

export type CandidateDetail = {
  id: string;
  episode_id: string;
  type: string;
  status: string;
  title_hint: string;
  start_time: number;
  end_time: number;
  duration_seconds: number;
  scores: Record<string, number>;
  metadata: Record<string, unknown>;
  shots: Shot[];
  transcript_segments: TranscriptSegment[];
  short_clip_path?: string | null;
  short_clip_error?: string | null;
  preview_clip_path?: string | null;
  preview_clip_error?: string | null;
  render_config?: ShortClipRenderConfig;
  has_edited_ass?: boolean;
  composite?: boolean;
  primary_span_index?: number;
  clip_spans?: ClipSpan[];
};

export type ShortClipSubtitleStyle = {
  font_family: string;
  font_size: number;
  alignment: number;
  margin_v: number;
  outline: number;
  primary_color: string;
  outline_color: string;
  shadow: number;
  background_box: boolean;
  bold: boolean;
};

export type ShortClipSubtitleOverride = {
  segment_id: string;
  text: string;
};

export type ShortClipRenderConfig = {
  trim_start?: number | null;
  trim_end?: number | null;
  burn_subtitles: boolean;
  subtitle_source: "none" | "file" | "transcript" | "edited-ass";
  aspect_ratio: "9:16" | "1:1" | "16:9";
  fit_mode: "cover" | "contain" | "pad-blur";
  quality_preset: "draft" | "standard" | "high";
  resolution_preset: string;
  width: number;
  height: number;
  subtitle_style?: ShortClipSubtitleStyle | null;
  subtitle_text_overrides?: ShortClipSubtitleOverride[] | null;
  use_imported_subtitles?: boolean;
  use_edited_ass?: boolean;
};

export type EpisodeTimeline = {
  episode_id: string;
  shots: Shot[];
  transcript_segments: TranscriptSegment[];
};

export type ScriptDraft = {
  id: string;
  version_no: number;
  language: string;
  hook_text: string;
  body_text: string;
  cta_text: string;
  full_script_text: string;
  estimated_duration_seconds: number;
  title_options: string[];
  is_selected: boolean;
  metadata: Record<string, unknown>;
};

export type ScriptDraftListResponse = {
  items: ScriptDraft[];
};

export type VideoDraftSummary = {
  id: string;
  candidate_id: string;
  script_draft_id: string;
  version_no: number;
  status: string;
  template_type: string;
  tts_voice_key?: string | null;
  draft_video_path?: string | null;
  thumbnail_path?: string | null;
  metadata: Record<string, unknown>;
};

export type VideoDraftListResponse = {
  items: VideoDraftSummary[];
  total: number;
};

export type VideoDraftDetail = {
  id: string;
  candidate_id: string;
  script_draft_id: string;
  version_no: number;
  status: string;
  template_type: string;
  tts_voice_key?: string | null;
  aspect_ratio: string;
  width: number;
  height: number;
  draft_video_path?: string | null;
  subtitle_path?: string | null;
  thumbnail_path?: string | null;
  burned_caption: boolean;
  render_config: Record<string, unknown>;
  timeline_json: Record<string, unknown>;
  operator_notes?: string | null;
  metadata: Record<string, unknown>;
};

export type TtsSegmentMetadata = {
  path: string;
  provider: string;
  voice_key: string;
  fallback_reason?: string | null;
  requested_duration_sec: number;
  actual_audio_duration_sec: number;
  final_segment_duration_sec: number;
};

export type ExportDetail = {
  id: string;
  video_draft_id: string;
  status: string;
  export_preset: string;
  export_video_path?: string | null;
  export_subtitle_path?: string | null;
  export_script_path?: string | null;
  export_metadata_path?: string | null;
  file_size_bytes?: number | null;
  metadata: Record<string, unknown>;
};
