import { describe, expect, it } from "vitest";
import { activeDisplayAt, buildDisplayTrack } from "./displayTrack";
import type { SessionEntry } from "../types";

const MIN_DWELL_S = 2.5; // matches DEFAULT_DISPLAY_CONFIG

const entry = (capture_t_s: number, text: string): SessionEntry => ({
  capture_t_s,
  text,
  capture_ms: 0,
  upload_ms: 0,
  inference_ms: 0,
  download_ms: 0,
  e2e_ms: 0,
  server_total_ms: 0,
  image_width: 0,
  image_height: 0,
});

const calm = (t: number, suffix = "") =>
  entry(t, `Empty road, clear conditions${suffix}. Advice: maintain speed.`);
const calmAlt = (t: number) =>
  entry(t, "Highway flowing smoothly, no traffic. Advice: maintain speed.");
const cautious = (t: number) =>
  entry(t, "Pedestrians on sidewalk ahead. Advice: slow down.");
const urgent = (t: number) =>
  entry(t, "Lead car braking hard. Advice: brake now.");
const urgentB = (t: number) =>
  entry(t, "Vehicle stopped ahead. Advice: brake now.");
const collision = (t: number) =>
  entry(t, "Collision imminent ahead. Advice: brake now.");

describe("buildDisplayTrack — basics", () => {
  it("returns an empty track for empty input", () => {
    expect(buildDisplayTrack([])).toEqual([]);
  });

  it("returns a single block for one entry, with endTime Infinity", () => {
    const track = buildDisplayTrack([calm(0)]);
    expect(track).toHaveLength(1);
    expect(track[0].startTime).toBe(0);
    expect(track[0].endTime).toBe(Infinity);
    expect(track[0].wasPreempted).toBe(false);
  });
});

describe("buildDisplayTrack — dwell + similarity", () => {
  it("drops entries inside the dwell window when no urgency", () => {
    // Two calms at t=0 and t=1: t=1 is inside dwell, no urgency, should be dropped.
    const track = buildDisplayTrack([calm(0), calm(1)]);
    expect(track).toHaveLength(1);
    expect(track[0].sourceEntry.capture_t_s).toBe(0);
  });

  it("extends current block past dwell when text is similar", () => {
    // Two near-identical calm captions, second past dwell. Same Advice and
    // observations share most words — should NOT open a new block.
    const track = buildDisplayTrack([calm(0), calm(MIN_DWELL_S + 0.1)]);
    expect(track).toHaveLength(1);
  });

  it("opens a new block past dwell when observation differs significantly", () => {
    const track = buildDisplayTrack([calm(0), calmAlt(MIN_DWELL_S + 0.1)]);
    expect(track).toHaveLength(2);
    expect(track[1].sourceEntry.capture_t_s).toBe(MIN_DWELL_S + 0.1);
    expect(track[0].endTime).toBe(MIN_DWELL_S + 0.1);
    expect(track[1].wasPreempted).toBe(false);
  });

  it("opens a new block past dwell when Advice changes", () => {
    const track = buildDisplayTrack([calm(0), cautious(MIN_DWELL_S + 0.1)]);
    expect(track).toHaveLength(2);
    expect(track[1].text).toMatch(/slow down/);
  });
});

describe("buildDisplayTrack — preempt path", () => {
  it("preempts inside dwell when Advice escalates calm -> urgent", () => {
    const track = buildDisplayTrack([calm(0), urgent(1)]);
    expect(track).toHaveLength(2);
    expect(track[0].endTime).toBe(1);
    expect(track[1].startTime).toBe(1);
    expect(track[1].wasPreempted).toBe(true);
  });

  it("preempts when observation gains an urgency keyword", () => {
    // Both have Advice: brake now (same class), but the second adds
    // 'collision' in observation that wasn't present before.
    const calmBrake = entry(
      0,
      "Lead car slowing. Advice: brake.",
    );
    const collisionBrake = entry(
      1,
      "Collision imminent. Advice: brake now.",
    );
    const track = buildDisplayTrack([calmBrake, collisionBrake]);
    expect(track).toHaveLength(2);
    expect(track[1].wasPreempted).toBe(true);
  });

  it("does not chain preempts: sustained urgency stays in one block", () => {
    // First urgent at t=0, second urgent inside dwell (t=1). No further
    // escalation possible (urgent is the top class) and the second has no
    // new urgency keyword. Should NOT open a new block.
    const track = buildDisplayTrack([urgent(0), urgentB(1)]);
    expect(track).toHaveLength(1);
  });

  it("after a preempt, the preempted block is pinned for full MIN_DWELL", () => {
    // calm @0, urgent @1 (preempt), calm @2 (inside the preempted block's
    // dwell — t=1 to t=3.5). The trailing calm should NOT reopen anything.
    const track = buildDisplayTrack([calm(0), urgent(1), calm(2)]);
    expect(track).toHaveLength(2);
    expect(track[1].text).toMatch(/brake now/);
    expect(track[1].wasPreempted).toBe(true);
    // Last block runs to Infinity — calm@2 was inside its dwell and
    // doesn't escalate, so it's dropped.
    expect(track[1].endTime).toBe(Infinity);
  });

  it("urgency keyword after dwell still opens a (non-preempt) block", () => {
    // Not strictly testing preempt — tests that the past-dwell path also
    // works when Advice didn't change but the keyword arrived later.
    const track = buildDisplayTrack([calm(0), collision(MIN_DWELL_S + 0.1)]);
    expect(track).toHaveLength(2);
    // This is a past-dwell open (not a preempt), but the Advice did
    // change (urgent), so meaningfullyDifferent is true.
    expect(track[1].wasPreempted).toBe(false);
  });
});

describe("activeDisplayAt", () => {
  it("returns null before the first block", () => {
    const track = buildDisplayTrack([calm(2)]);
    expect(activeDisplayAt(track, 1.0)).toBeNull();
  });

  it("returns the block whose [startTime, endTime) contains t", () => {
    const track = buildDisplayTrack([calm(0), urgent(1)]);
    expect(activeDisplayAt(track, 0.5)?.text).toMatch(/maintain/);
    expect(activeDisplayAt(track, 1.5)?.text).toMatch(/brake/);
  });

  it("returns the last block when t is past every startTime", () => {
    const track = buildDisplayTrack([calm(0)]);
    expect(activeDisplayAt(track, 9999)?.startTime).toBe(0);
  });
});
