import {
  DEFAULT_DISPLAY_CONFIG,
  type DisplayConfig,
  type DisplayEntry,
  type SessionEntry,
} from "../types";
import {
  classifyAdvice,
  containsUrgencyKeyword,
  escalates,
  splitObservationAdvice,
} from "./urgency";

// Tokenise an observation into a Set of lowercase word stems for Jaccard
// comparison. Punctuation is stripped; very short tokens are dropped.
function tokenise(observation: string): Set<string> {
  return new Set(
    observation
      .toLowerCase()
      .replace(/[^\p{L}\p{N}\s]/gu, " ")
      .split(/\s+/)
      .filter((w) => w.length > 2),
  );
}

function jaccard(a: Set<string>, b: Set<string>): number {
  if (a.size === 0 && b.size === 0) return 1;
  let intersection = 0;
  for (const x of a) if (b.has(x)) intersection++;
  const union = a.size + b.size - intersection;
  return union === 0 ? 1 : intersection / union;
}

function meaningfullyDifferent(
  prev: SessionEntry,
  next: SessionEntry,
  jaccardThreshold: number,
): boolean {
  const prevSplit = splitObservationAdvice(prev.text);
  const nextSplit = splitObservationAdvice(next.text);
  if (prevSplit.advice !== nextSplit.advice) return true;
  return (
    jaccard(tokenise(prevSplit.observation), tokenise(nextSplit.observation)) <
    jaccardThreshold
  );
}

function shouldPreempt(
  current: SessionEntry,
  candidate: SessionEntry,
): boolean {
  const currentClass = classifyAdvice(current.text);
  const candidateClass = classifyAdvice(candidate.text);
  if (escalates(currentClass, candidateClass)) return true;
  // Observation-keyword preempt fires only when the candidate has a keyword
  // the current displayed caption did not — sustained collisions don't cause
  // repeated preempts.
  return (
    containsUrgencyKeyword(candidate.text) &&
    !containsUrgencyKeyword(current.text)
  );
}

/**
 * Build a display schedule from raw session entries.
 *
 * Assumes `entries` is sorted by `capture_t_s` ascending (the recorder writes
 * them in this order).
 *
 * The output is a list of `DisplayEntry` blocks with non-overlapping
 * [startTime, endTime) intervals; the last block has `endTime: Infinity`.
 *
 * See plan: "Subtitle selection — display track with urgency override".
 */
export function buildDisplayTrack(
  entries: SessionEntry[],
  config: DisplayConfig = DEFAULT_DISPLAY_CONFIG,
): DisplayEntry[] {
  const track: DisplayEntry[] = [];
  if (entries.length === 0) return track;

  const minDwellS = config.minDwellMs / 1000;

  // Helper: open a new block at the given entry. When closing the previous
  // block (if any), set endTime to entry.capture_t_s.
  const open = (entry: SessionEntry, wasPreempted: boolean) => {
    if (track.length > 0) {
      track[track.length - 1].endTime = entry.capture_t_s;
    }
    track.push({
      startTime: entry.capture_t_s,
      endTime: Infinity,
      text: entry.text,
      sourceEntry: entry,
      wasPreempted,
    });
  };

  for (const entry of entries) {
    if (track.length === 0) {
      open(entry, false);
      continue;
    }
    const current = track[track.length - 1];
    const elapsed = entry.capture_t_s - current.startTime;

    if (elapsed < minDwellS) {
      // Inside dwell. The only way to swap is a hard-preempt.
      if (shouldPreempt(current.sourceEntry, entry)) {
        open(entry, true);
      }
      // Otherwise drop the entry.
      continue;
    }

    // Past dwell.
    if (
      meaningfullyDifferent(current.sourceEntry, entry, config.jaccardThreshold)
    ) {
      open(entry, false);
    }
    // else: extend current block (no-op; endTime stays Infinity).
  }

  return track;
}

// Find the active display block at video time t.
// Returns null when t is before the first block's startTime.
export function activeDisplayAt(
  track: DisplayEntry[],
  t: number,
): DisplayEntry | null {
  if (track.length === 0) return null;
  if (t < track[0].startTime) return null;
  // Binary search for the rightmost block with startTime <= t.
  let lo = 0;
  let hi = track.length - 1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >>> 1;
    if (track[mid].startTime <= t) lo = mid;
    else hi = mid - 1;
  }
  const block = track[lo];
  return t < block.endTime ? block : null;
}
