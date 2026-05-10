import { useEffect, useRef } from "react";
import type { DisplayEntry, SessionEntry } from "../types";
import { containsUrgencyKeyword } from "../lib/urgency";

interface Props {
  entries: SessionEntry[];
  visibleCount: number;
  active: DisplayEntry | null;
}

function formatTimestamp(t: number): string {
  const total = Math.max(0, Math.round(t));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

// Right rail: every raw caption, newest at the bottom; auto-scrolls to keep
// the latest entry in view. Active subtitle source gets a left accent bar;
// preempt-triggering captions get a small amber dot.
export function CommentaryLog({ entries, visibleCount, active }: Props) {
  const scrollerRef = useRef<HTMLDivElement | null>(null);
  const visible = entries.slice(0, visibleCount);

  useEffect(() => {
    const el = scrollerRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [visibleCount]);

  const activeT = active?.sourceEntry.capture_t_s;

  return (
    <aside className="commentary-log">
      <header className="commentary-log__header">
        <span className="commentary-log__title">Live commentary</span>
        <span className="commentary-log__count">
          {visibleCount} / {entries.length}
        </span>
      </header>
      <div className="commentary-log__scroller" ref={scrollerRef}>
        {visible.map((entry) => {
          const isActive = entry.capture_t_s === activeT;
          const hasUrgency = containsUrgencyKeyword(entry.text);
          return (
            <div
              key={entry.capture_t_s}
              className={[
                "log-row",
                isActive ? "log-row--active" : "",
                hasUrgency ? "log-row--urgent" : "",
              ]
                .filter(Boolean)
                .join(" ")}
            >
              <div className="log-row__meta">
                <span className="log-row__ts">
                  {formatTimestamp(entry.capture_t_s)}
                </span>
                {hasUrgency && <span className="log-row__urgency-dot" />}
                <span className="log-row__latency">
                  {Math.round(entry.e2e_ms)}ms
                </span>
              </div>
              <div className="log-row__text">{entry.text}</div>
            </div>
          );
        })}
        {visible.length === 0 && (
          <div className="log-row log-row--empty">
            Waiting for first frame to be analysed…
          </div>
        )}
      </div>
    </aside>
  );
}
