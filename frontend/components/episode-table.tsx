"use client";

import Link from "next/link";
import { Episode } from "@/lib/types";
import { formatDuration, formatEpisodeLabel } from "@/lib/format";
import { StatusBadge } from "@/components/status-badge";
import {
  AnalyzeEpisodeButton,
  ClearEpisodeAnalysisButton,
  DeleteEpisodeButton
} from "@/components/mutation-buttons";

type Props = {
  episodes: Episode[];
};

export function EpisodeTable({ episodes }: Props) {
  return (
    <div className="panel">
      <table className="table">
        <thead>
          <tr>
            <th>작품</th>
            <th>시즌/회</th>
            <th>채널</th>
            <th>상태</th>
            <th>길이</th>
            <th>동작</th>
          </tr>
        </thead>
        <tbody>
          {episodes.map((episode) => (
            <tr key={episode.id}>
              <td>
                <div className="stack">
                  <strong>{episode.show_title}</strong>
                  <span className="muted">{episode.episode_title ?? "제목 없음"}</span>
                </div>
              </td>
              <td>{formatEpisodeLabel(episode.season_number, episode.episode_number)}</td>
              <td>{episode.target_channel}</td>
              <td>
                <StatusBadge value={episode.status} />
              </td>
              <td>{formatDuration(episode.duration_seconds)}</td>
              <td>
                <div className="row wrap">
                  <Link href={`/episodes/${episode.id}`} className="link-button">
                    상세
                  </Link>
                  <Link href={`/episodes/${episode.id}/candidates`} className="link-button">
                    후보
                  </Link>
                  <AnalyzeEpisodeButton episodeId={episode.id} />
                  <ClearEpisodeAnalysisButton episodeId={episode.id} />
                  <DeleteEpisodeButton episodeId={episode.id} />
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
