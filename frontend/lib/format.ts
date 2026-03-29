export function formatDuration(seconds?: number | null): string {
  if (seconds == null || Number.isNaN(seconds)) return "-";
  const total = Math.round(seconds);
  const minutes = Math.floor(total / 60);
  const remainingSeconds = total % 60;
  if (minutes === 0) return `${remainingSeconds}s`;
  return `${minutes}m ${remainingSeconds.toString().padStart(2, "0")}s`;
}

export function formatTimecode(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(total / 60);
  const remainder = total % 60;
  return `${minutes.toString().padStart(2, "0")}:${remainder.toString().padStart(2, "0")}`;
}

export function formatPreciseTimecode(seconds: number): string {
  const safe = Math.max(0, Number.isFinite(seconds) ? seconds : 0);
  const minutes = Math.floor(safe / 60);
  const remainder = safe - minutes * 60;
  return `${minutes.toString().padStart(2, "0")}:${remainder.toFixed(3).padStart(6, "0")}`;
}

export function parseTimecodeInput(input: string): number | null {
  const raw = input.trim();
  if (!raw) return null;
  if (raw.includes(":")) {
    const [minutesPart, secondsPart] = raw.split(":", 2);
    const minutes = Number.parseInt(minutesPart, 10);
    const seconds = Number.parseFloat(secondsPart);
    if (!Number.isFinite(minutes) || !Number.isFinite(seconds)) return null;
    return minutes * 60 + seconds;
  }
  const parsed = Number.parseFloat(raw);
  return Number.isFinite(parsed) ? parsed : null;
}

export function formatEpisodeLabel(season?: number | null, episode?: number | null): string {
  if (season == null && episode == null) return "-";
  return `S${season ?? "?"}E${episode ?? "?"}`;
}
