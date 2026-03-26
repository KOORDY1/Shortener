"use client";

import { formatDuration, formatTimecode } from "@/lib/format";
import type { ClipSpan, Shot } from "@/lib/types";

type Props = {
  spans: ClipSpan[];
  shots: Shot[];
  activeSpanIndex: number;
  onSelectSpan: (index: number) => void;
  onPlayFromSpan: (index: number) => void;
};

export function CompositeSpanPreview({
  spans,
  shots,
  activeSpanIndex,
  onSelectSpan,
  onPlayFromSpan
}: Props) {
  return (
    <div className="panel stack">
      <h2 className="section-title">Composite Span Preview</h2>
      <div className="stack">
        {spans.map((span, index) => {
          const relatedShots = shots.filter(
            (shot) => shot.start_time <= span.end_time && shot.end_time >= span.start_time
          );
          const isActive = activeSpanIndex === index;
          return (
            <div key={`${span.order}-${index}`} className="panel soft stack">
              <div className="spaced">
                <strong>
                  #{index + 1} {span.role ?? (index === 0 ? "primary" : "span")}
                </strong>
                {isActive ? <span className="badge running">현재 span</span> : null}
              </div>
              <div className="muted">
                {formatTimecode(span.start_time)} - {formatTimecode(span.end_time)} /{" "}
                {formatDuration(span.end_time - span.start_time)}
              </div>
              {relatedShots.length > 0 ? (
                <div className="shot-strip">
                  {relatedShots.slice(0, 6).map((shot) => (
                    <div key={shot.id} className="shot-tile">
                      <div className="thumbnail small">#{shot.shot_index}</div>
                      <div className="muted tiny">
                        {formatTimecode(shot.start_time)} – {formatTimecode(shot.end_time)}
                      </div>
                    </div>
                  ))}
                </div>
              ) : null}
              <div className="row wrap">
                <button type="button" className="button ghost" onClick={() => onSelectSpan(index)}>
                  이 span 보기
                </button>
                <button type="button" className="button ghost" onClick={() => onPlayFromSpan(index)}>
                  이 span부터 재생
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
