import { useMemo, useRef } from "react";
import { activeDisplayAt } from "../lib/displayTrack";
import type { DisplayEntry } from "../types";

interface ActiveDisplay {
  active: DisplayEntry | null;
  isNew: boolean;
  wasPreempted: boolean;
}

// Returns the active block at currentTime plus a transient `isNew` flag that
// flips true on the render where the active block changes. SubtitleOverlay
// uses this to drive a one-shot fade-in; the preempt accent re-fires from
// `wasPreempted` of the active block.
export function useActiveDisplay(
  track: DisplayEntry[],
  currentTime: number,
): ActiveDisplay {
  const lastStartTime = useRef<number | null>(null);

  const active = useMemo(
    () => activeDisplayAt(track, currentTime),
    [track, currentTime],
  );

  const startTime = active ? active.startTime : null;
  const isNew = startTime !== lastStartTime.current;
  lastStartTime.current = startTime;

  return {
    active,
    isNew,
    wasPreempted: active?.wasPreempted ?? false,
  };
}
