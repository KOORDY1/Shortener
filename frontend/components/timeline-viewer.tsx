import { EpisodeTimeline } from "@/lib/types";
import { formatTimecode } from "@/lib/format";

type Props = {
  timeline: EpisodeTimeline;
};

export function TimelineViewer({ timeline }: Props) {
  return (
    <div className="panel">
      <h2 className="section-title">타임라인</h2>
      <div className="timeline">
        <div>
          <p className="muted">샷</p>
          <div className="timeline-row">
            {timeline.shots.map((shot) => (
              <div className="timeline-block" key={shot.id}>
                <strong>#{shot.shot_index}</strong>
                <div>
                  {formatTimecode(shot.start_time)} - {formatTimecode(shot.end_time)}
                </div>
              </div>
            ))}
          </div>
        </div>
        <div>
          <p className="muted">자막·대본</p>
          <div className="stack">
            {timeline.transcript_segments.length === 0 ? (
              <p className="muted tiny">
                업로드 시 SRT/WebVTT를 함께 넣거나, 쇼츠 패널에서 자막을 가져오면 표시됩니다. 가짜 예시 대본은
                넣지 않습니다.
              </p>
            ) : (
              timeline.transcript_segments.map((segment) => (
                <div className="timeline-block" key={segment.id}>
                  <strong>
                    {formatTimecode(segment.start_time)} - {formatTimecode(segment.end_time)}
                  </strong>
                  <div>{segment.text}</div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
