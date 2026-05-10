import { useEffect, useRef, useState } from "react";
import type { DisplayEntry, SessionEntry } from "../types";

interface Props {
  cadenceS: number;
  framesAnalysed: number;
  active: DisplayEntry | null;
  recentEntry: SessionEntry | null;
}

// Top strip across the video stage. Shows: cadence (static), most-recent
// e2e_ms (pulses on update, amber on preempt), frames-analysed counter.
export function HUD({ cadenceS, framesAnalysed, active, recentEntry }: Props) {
  const [latencyPulse, setLatencyPulse] = useState(0);
  const [preemptPulse, setPreemptPulse] = useState(0);
  const lastEntryT = useRef<number | null>(null);
  const lastActiveStart = useRef<number | null>(null);

  useEffect(() => {
    const t = recentEntry?.capture_t_s ?? null;
    if (t !== null && t !== lastEntryT.current) {
      lastEntryT.current = t;
      setLatencyPulse((n) => n + 1);
    }
  }, [recentEntry]);

  useEffect(() => {
    const start = active?.startTime ?? null;
    if (start !== null && start !== lastActiveStart.current) {
      lastActiveStart.current = start;
      if (active?.wasPreempted) setPreemptPulse((n) => n + 1);
    }
  }, [active]);

  const e2e = recentEntry ? Math.round(recentEntry.e2e_ms) : null;
  const inf = recentEntry ? Math.round(recentEntry.inference_ms) : null;

  return (
    <div className={`hud ${active?.wasPreempted ? "hud--alert" : ""}`}>
      <div className="hud__brand">
        <span className="hud__dot" />
        VLM-narrated dashcam
      </div>
      <div className="hud__stats">
        <Stat label="cadence" value={`${cadenceS.toFixed(1)} s`} />
        <Stat
          key={`lat-${latencyPulse}-${preemptPulse}`}
          label="e2e"
          value={e2e !== null ? `${e2e} ms` : "—"}
          modifier={
            preemptPulse > 0 && active?.wasPreempted ? "alert" : "pulse"
          }
        />
        <Stat
          label="inference"
          value={inf !== null ? `${inf} ms` : "—"}
          subdued
        />
        <Stat label="frames" value={String(framesAnalysed)} />
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  modifier,
  subdued,
}: {
  label: string;
  value: string;
  modifier?: "pulse" | "alert";
  subdued?: boolean;
}) {
  const cls = [
    "hud__stat",
    modifier ? `hud__stat--${modifier}` : "",
    subdued ? "hud__stat--subdued" : "",
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <div className={cls}>
      <span className="hud__stat-label">{label}</span>
      <span className="hud__stat-value">{value}</span>
    </div>
  );
}
