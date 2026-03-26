/** API 값은 유지하고 화면에만 쓰는 한국어 라벨 */

const BADGE_LABELS: Record<string, string> = {
  generated: "생성됨",
  selected: "선택됨",
  rejected: "거절됨",
  drafted: "초안",
  uploaded: "업로드됨",
  processing: "처리 중",
  ready: "준비됨",
  failed: "실패",
  low: "낮음",
  medium: "보통",
  high: "높음",
  context_commentary: "맥락 해설",
  queued: "대기",
  running: "진행 중",
  succeeded: "완료",
  cancelled: "취소",
  analysis: "분석",
  script_generation: "스크립트 생성",
  video_draft_render: "비디오 초안 렌더",
  export_render: "보내기 렌더",
  short_clip_render: "쇼츠 클립 렌더",
  ingest_episode: "에피소드 수집",
  created: "생성",
  approved: "승인",
  completed: "완료",
  composite: "복합 후보"
};

export function badgeLabel(value: string): string {
  const key = value.toLowerCase();
  return BADGE_LABELS[key] ?? value;
}

export function jobTypeLabel(type: string): string {
  return BADGE_LABELS[type.toLowerCase()] ?? type;
}

export function scoreKeyLabel(key: string): string {
  const m: Record<string, string> = {
    total_score: "총점",
    hook_score: "훅",
    clarity_score: "명확도",
    commentary_score: "해설 적합도",
    comedy_score: "코미디 감도",
    emotion_score: "감동 감도",
    visual_hook_score: "시각 훅",
    self_contained_score: "자체 완결성",
    emotion_shift_score: "감정 변화",
    thumbnail_strength_score: "썸네일 강도",
    vision_score_delta: "비전 가산점"
  };
  return m[key] ?? key;
}
