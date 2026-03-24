"use client";

import Link from "next/link";
import { Episode } from "@/lib/types";
import { formatDuration, formatEpisodeLabel } from "@/lib/format";
import { StatusBadge } from "@/components/status-badge";
import { AnalyzeEpisodeButton } from "@/components/mutation-buttons";

type Props = {
  episodes: Episode[];
};

export function EpisodeTable({ episodes }: Props) {
  return (
    <div className="panel">
      <table className="table">
        <thead>
          <tr>
            <th>Show</th>
            <th>S/E</th>
            <th>Target</th>
            <th>Status</th>
            <th>Duration</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {episodes.map((episode) => (
            <tr key={episode.id}>
              <td>
                <div className="stack">
                  <strong>{episode.show_title}</strong>
                  <span className="muted">{episode.episode_title ?? "Untitled episode"}</span>
                </div>
              </td>
              <td>{formatEpisodeLabel(episode.season_number, episode.episode_number)}</td>
              <td>{episode.target_channel}</td>
              <td>
                <StatusBadge value={episode.status} />
              </td>
              <td>{formatDuration(episode.duration_seconds)}</td>
              <td>
                <div className="row">
                  <Link href={`/episodes/${episode.id}`} className="link-button">
                    Open
                  </Link>
                  <Link href={`/episodes/${episode.id}/candidates`} className="link-button">
                    Candidates
                  </Link>
                  <AnalyzeEpisodeButton episodeId={episode.id} />
                </div>
              </td>
            </tr>
          ))}
          {episodes.length === 0 ? (
            <tr>
              <td colSpan={6} className="muted">
                에피소드가 없습니다.
              </td>
            </tr>
          ) : null}
        </tbody>
      </table>
    </div>
  );
}
