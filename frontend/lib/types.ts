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
  risk_score: number;
  risk_level: string;
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
  risk: {
    risk_score: number;
    risk_level: string;
    reasons: string[];
  };
  metadata: Record<string, unknown>;
  shots: Shot[];
  transcript_segments: TranscriptSegment[];
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
