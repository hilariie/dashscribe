import type { SessionEntry } from "../types";

export class SessionParseError extends Error {
  constructor(
    message: string,
    public readonly line: number,
  ) {
    super(`${message} (line ${line})`);
    this.name = "SessionParseError";
  }
}

const REQUIRED_KEYS: ReadonlyArray<keyof SessionEntry> = [
  "capture_t_s",
  "text",
  "capture_ms",
  "upload_ms",
  "inference_ms",
  "download_ms",
  "e2e_ms",
  "server_total_ms",
  "image_width",
  "image_height",
];

export function parseJsonl(raw: string): SessionEntry[] {
  const entries: SessionEntry[] = [];
  const lines = raw.split("\n");
  for (let i = 0; i < lines.length; i++) {
    const trimmed = lines[i].trim();
    if (trimmed === "") continue;
    let parsed: unknown;
    try {
      parsed = JSON.parse(trimmed);
    } catch {
      throw new SessionParseError("invalid JSON", i + 1);
    }
    if (typeof parsed !== "object" || parsed === null) {
      throw new SessionParseError("entry is not an object", i + 1);
    }
    const obj = parsed as Record<string, unknown>;
    for (const key of REQUIRED_KEYS) {
      if (!(key in obj)) {
        throw new SessionParseError(`missing key '${key}'`, i + 1);
      }
    }
    entries.push(obj as unknown as SessionEntry);
  }
  return entries;
}

// Given a session JSONL path/URL, return the conventional sibling TTS audio
// path produced by client/render_tts.py: same parent, replace the .jsonl (or
// trailing) extension with .tts.mp3. Used by App.tsx to fetch-and-fallback in
// the ?session=... query-param path.
export function inferTtsPath(jsonlPath: string): string {
  const stripped = jsonlPath.replace(/\.[^./]+$/, "");
  return `${stripped}.tts.mp3`;
}

// Median of consecutive capture_t_s diffs. Robust to inference-jitter outliers
// because the recorder's stride is fixed in *video* time, but using a median
// keeps things honest when the source video skips frames or the recorder is
// resumed mid-session.
export function cadenceFromEntries(entries: SessionEntry[]): number {
  if (entries.length < 2) return 0;
  const diffs: number[] = [];
  for (let i = 1; i < entries.length; i++) {
    diffs.push(entries[i].capture_t_s - entries[i - 1].capture_t_s);
  }
  diffs.sort((a, b) => a - b);
  const mid = Math.floor(diffs.length / 2);
  return diffs.length % 2 === 0
    ? (diffs[mid - 1] + diffs[mid]) / 2
    : diffs[mid];
}
