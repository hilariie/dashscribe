import { useEffect, useRef, useState } from "react";
import type { DisplayEntry } from "../types";
import { splitObservationAdvice } from "../lib/urgency";

interface Props {
  active: DisplayEntry | null;
}

// Renders the active subtitle with a CSS-only fade-in / fade-out and an
// amber-flash backing strip when the active block was preempted.
//
// Implementation: when the active block's startTime changes, we bump a key
// on the inner element so the fade-in keyframe re-fires; the previous text
// stays in the DOM for fade-out via a "leaving" state.
export function SubtitleOverlay({ active }: Props) {
  const [leaving, setLeaving] = useState<DisplayEntry | null>(null);
  const prev = useRef<DisplayEntry | null>(null);

  useEffect(() => {
    const prevActive = prev.current;
    if (prevActive && (!active || prevActive.startTime !== active.startTime)) {
      setLeaving(prevActive);
      const t = window.setTimeout(() => setLeaving(null), 250); // matches --fade-out
      prev.current = active;
      return () => window.clearTimeout(t);
    }
    prev.current = active;
  }, [active]);

  return (
    <div className="subtitle-overlay" aria-live="polite">
      {leaving && (
        <SubtitleStrip
          key={`leaving-${leaving.startTime}`}
          entry={leaving}
          state="leaving"
        />
      )}
      {active && (
        <SubtitleStrip
          key={`enter-${active.startTime}`}
          entry={active}
          state="entering"
        />
      )}
    </div>
  );
}

function SubtitleStrip({
  entry,
  state,
}: {
  entry: DisplayEntry;
  state: "entering" | "leaving";
}) {
  const { observation, advice } = splitObservationAdvice(entry.text);
  const obsCap = observation
    ? observation.charAt(0).toUpperCase() + observation.slice(1)
    : "";
  return (
    <div
      className={[
        "subtitle-strip",
        `subtitle-strip--${state}`,
        entry.wasPreempted ? "subtitle-strip--preempt" : "",
      ]
        .filter(Boolean)
        .join(" ")}
    >
      {obsCap && <span className="subtitle-strip__observation">{obsCap}</span>}
      {advice && (
        <span className="subtitle-strip__advice">
          <span className="subtitle-strip__advice-label">Advice</span>
          <span className="subtitle-strip__advice-text">
            {advice.replace(/\.$/, "")}
          </span>
        </span>
      )}
    </div>
  );
}
