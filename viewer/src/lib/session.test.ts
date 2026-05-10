import { describe, expect, it } from "vitest";
import {
  cadenceFromEntries,
  inferTtsPath,
  parseJsonl,
  SessionParseError,
} from "./session";
import type { SessionEntry } from "../types";

const validRow = (capture_t_s: number, text = "Clear road. Advice: maintain speed."): string =>
  JSON.stringify({
    capture_t_s,
    text,
    capture_ms: 4.0,
    upload_ms: 290.0,
    inference_ms: 1180.0,
    download_ms: 50.0,
    e2e_ms: 1524.0,
    server_total_ms: 1183.0,
    image_width: 1920,
    image_height: 1080,
  });

describe("parseJsonl", () => {
  it("parses three lines into three entries", () => {
    const raw = [validRow(0), validRow(1), validRow(2)].join("\n");
    const entries = parseJsonl(raw);
    expect(entries).toHaveLength(3);
    expect(entries[0].capture_t_s).toBe(0);
    expect(entries[2].capture_t_s).toBe(2);
  });

  it("ignores trailing blank lines", () => {
    const raw = [validRow(0), validRow(1), "", "  ", ""].join("\n");
    expect(parseJsonl(raw)).toHaveLength(2);
  });

  it("throws SessionParseError with line number on malformed JSON", () => {
    const raw = [validRow(0), "{not json", validRow(2)].join("\n");
    expect(() => parseJsonl(raw)).toThrow(SessionParseError);
    try {
      parseJsonl(raw);
    } catch (e) {
      expect((e as SessionParseError).line).toBe(2);
    }
  });

  it("throws when a required key is missing", () => {
    const raw = JSON.stringify({ capture_t_s: 0, text: "x" });
    expect(() => parseJsonl(raw)).toThrow(/missing key/);
  });

  it("returns an empty array for empty input", () => {
    expect(parseJsonl("")).toEqual([]);
    expect(parseJsonl("\n\n  \n")).toEqual([]);
  });
});

describe("cadenceFromEntries", () => {
  const make = (times: number[]): SessionEntry[] =>
    times.map(
      (t) =>
        ({
          capture_t_s: t,
          text: "",
          capture_ms: 0,
          upload_ms: 0,
          inference_ms: 0,
          download_ms: 0,
          e2e_ms: 0,
          server_total_ms: 0,
          image_width: 0,
          image_height: 0,
        }) as SessionEntry,
    );

  it("returns 1.0 on a uniform 1 s session", () => {
    expect(cadenceFromEntries(make([0, 1, 2, 3, 4]))).toBe(1.0);
  });

  it("returns 0 when fewer than two entries", () => {
    expect(cadenceFromEntries([])).toBe(0);
    expect(cadenceFromEntries(make([5]))).toBe(0);
  });

  it("uses the median so a single jitter outlier doesn't drag the cadence", () => {
    // Most diffs are 1.0; one is 5.0 (a stalled frame). Mean would be ~1.66;
    // median should still report 1.0.
    const entries = make([0, 1, 2, 3, 8, 9, 10]);
    expect(cadenceFromEntries(entries)).toBe(1.0);
  });
});

describe("inferTtsPath", () => {
  it("replaces .jsonl with .tts.mp3 in /data/-style URLs", () => {
    expect(inferTtsPath("/data/session-video1.jsonl")).toBe(
      "/data/session-video1.tts.mp3",
    );
  });

  it("replaces non-jsonl extensions too", () => {
    expect(inferTtsPath("/data/session-video1.json")).toBe(
      "/data/session-video1.tts.mp3",
    );
  });

  it("appends .tts.mp3 when there is no extension", () => {
    expect(inferTtsPath("/data/session")).toBe("/data/session.tts.mp3");
  });

  it("does not strip extensions inside parent directories", () => {
    expect(inferTtsPath("/data.dir/session.jsonl")).toBe(
      "/data.dir/session.tts.mp3",
    );
  });
});
