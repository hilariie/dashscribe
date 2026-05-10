// Canonical contract with client/capture.py:build_session_entry. Any field
// added/removed/renamed must be done in lockstep.
export interface SessionEntry {
  capture_t_s: number;
  text: string;
  capture_ms: number;
  upload_ms: number;
  inference_ms: number;
  download_ms: number;
  e2e_ms: number;
  server_total_ms: number;
  image_width: number;
  image_height: number;
}

export type AdviceClass = "calm" | "cautious" | "urgent";

export interface DisplayEntry {
  startTime: number;
  endTime: number;
  text: string;
  sourceEntry: SessionEntry;
  wasPreempted: boolean;
}

export interface DisplayConfig {
  minDwellMs: number;
  jaccardThreshold: number;
}

export const DEFAULT_DISPLAY_CONFIG: DisplayConfig = {
  minDwellMs: 2500,
  jaccardThreshold: 0.5,
};
