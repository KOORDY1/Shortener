import { EpisodeTimeline } from "@/lib/types";
import { formatTimecode } from "@/lib/format";

type Props = {
  timeline: EpisodeTimeline;
};

export function TimelineViewer({ timeline }: Props) {
  return (
    <div className="panel">
      <h2 className="section-title">Timeline</h2>
      <div className="timeline">
        <div>
          <p className="muted">Shots</p>
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
          <p className="muted">Transcript</p>
          <div className="stack">
            {timeline.transcript_segments.map((segment) => (
              <div className="timeline-block" key={segment.id}>
                <strong>
                  {formatTimecode(segment.start_time)} - {formatTimecode(segment.end_time)}
                </strong>
                <div>{segment.text}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
