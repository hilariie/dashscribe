"""M2 client: video frames -> /describe (with sliding window) -> printed commentary.

Opens a video file with OpenCV, samples one frame every CADENCE_S seconds of
video time, JPEG-encodes it, base64-encodes the bytes, POSTs to /describe over
a single persistent httpx.Client, prints the response with full latency
breakdown.

Sliding-window context: the client maintains two deques. The caption deque
(--context-text-n entries) holds recent assistant captions and is sent as
`recent_commentary`. The frame deque (--context-image-n entries; default 0)
holds recent base64 JPEGs and is sent as `recent_frames_b64`. Server caps
both server-side to prevent OOM regardless of client behaviour.

Scene-cut detection: when the input is a compilation, sliding-window context
must not bleed across cuts. Before adding each newly sampled frame to the
deques, the client compares its grayscale histogram to the previous sampled
frame (Bhattacharyya distance). If the distance exceeds
--scene-cut-threshold, both deques are cleared so the new scene starts with
empty context. Set --scene-cut-threshold 0 to disable.

Latency breakdown: client_send_ts and the response's server_recv_ts /
server_send_ts give an upload + inference + download split. The split is
biased by client/server clock skew (constant per session); the sum is
skew-invariant. Capture time is the client-side encode wall time.

Session output (M3): pass --session-out PATH to write one JSON line per
successful response. The viewer under viewer/ consumes this file and renders
captions against the original video aligned to capture_t_s.

The persistent connection is load-bearing: Track A measured p95 = 5.2 s
without keep-alive vs 2.77 s with it. See docs/latency_preflight.md.

    uv run python capture.py path/to/clip.mp4
    uv run python capture.py path/to/clip.mp4 --url http://vm:8000/describe \\
        --context-text-n 4 --context-image-n 1 \\
        --system-prompt-file ../prompts/system.txt
    uv run python capture.py path/to/clip.mp4 --cadence 1.0 \\
        --session-out ../data/session.jsonl
"""

import argparse
import base64
import json
import sys
import time
from collections import deque
from pathlib import Path

import cv2
import httpx
import numpy as np

DEFAULT_URL = "http://localhost:8000/describe"
DEFAULT_CADENCE_S = 3.0
# Text-only context measurably hurt single-frame quality during M2 iteration —
# the model treated prior captions as ground truth and either repeated them or
# anchored to stale observations. Keep the flag for experimentation but default
# to off.
DEFAULT_CONTEXT_TEXT_N = 0
# Multi-image input was tested as a motion-context window: 2 prior frames +
# current, with server-side auto-downscale to MULTI_IMAGE_MAX_SIDE (640px) so
# the request fits on a single A100. In M2 integration testing the multi-image
# captions were measurably worse than single-frame for this prompt, so the
# default is off. Flag retained for re-evaluation when the prompt or model
# changes; set to >0 to re-enable the motion window.
DEFAULT_CONTEXT_IMAGE_N = 0
# Bhattacharyya distance between consecutive sampled-frame grayscale
# histograms above this triggers a context reset. Hard cuts in compilations
# typically land 0.5-0.9; intra-scene motion stays under ~0.3. Set to 0 to
# disable detection entirely.
DEFAULT_SCENE_CUT_THRESHOLD = 0.5
JPEG_QUALITY = 85


def encode_frame_to_b64_jpeg(frame, quality: int = JPEG_QUALITY) -> str:
    ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        raise RuntimeError("cv2.imencode failed")
    return base64.b64encode(buf.tobytes()).decode("ascii")


def _gray_hist(frame_bgr: np.ndarray) -> np.ndarray:
    """64-bin L1-normalised grayscale histogram for shot-boundary detection."""
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    h = cv2.calcHist([gray], [0], None, [64], [0, 256])
    cv2.normalize(h, h, 1.0, 0.0, cv2.NORM_L1)
    return h


def hist_distance(prev_frame: np.ndarray, curr_frame: np.ndarray) -> float:
    """Bhattacharyya distance between grayscale histograms of two BGR frames.

    0.0 = identical distributions, 1.0 = disjoint. Hard cuts in dashcam
    compilations typically land in 0.5-0.9; intra-scene motion stays below
    ~0.3.
    """
    return float(
        cv2.compareHist(
            _gray_hist(prev_frame),
            _gray_hist(curr_frame),
            cv2.HISTCMP_BHATTACHARYYA,
        )
    )


def compute_timing_split(
    client_send_ts_ms: float,
    client_recv_ts_ms: float,
    server_recv_ts_ms: float,
    server_send_ts_ms: float,
) -> dict[str, float]:
    """Return upload/inference/download/e2e from a paired set of timestamps.

    Upload and download are skewed by the (unknown, constant) client/server
    clock offset; their sum equals e2e - inference and is skew-invariant.
    """
    return {
        "upload_ms": server_recv_ts_ms - client_send_ts_ms,
        "inference_ms": server_send_ts_ms - server_recv_ts_ms,
        "download_ms": client_recv_ts_ms - server_send_ts_ms,
        "e2e_ms": client_recv_ts_ms - client_send_ts_ms,
    }


def build_session_entry(
    capture_t_s: float,
    text: str,
    capture_ms: float,
    timing_split: dict[str, float],
    server_total_ms: float,
    image_width: int,
    image_height: int,
) -> dict:
    """Shape one JSONL row for the M3 viewer.

    Schema is the canonical contract between this recorder and viewer/. Any
    schema change must update viewer/src/types.ts SessionEntry in lockstep.
    """
    return {
        "capture_t_s": round(capture_t_s, 3),
        "text": text,
        "capture_ms": round(capture_ms, 2),
        "upload_ms": round(timing_split["upload_ms"], 2),
        "inference_ms": round(timing_split["inference_ms"], 2),
        "download_ms": round(timing_split["download_ms"], 2),
        "e2e_ms": round(timing_split["e2e_ms"], 2),
        "server_total_ms": round(server_total_ms, 2),
        "image_width": image_width,
        "image_height": image_height,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("video", help="Path to a video file readable by OpenCV.")
    parser.add_argument(
        "--url", default=DEFAULT_URL, help=f"Endpoint URL (default: {DEFAULT_URL})."
    )
    parser.add_argument(
        "--cadence",
        type=float,
        default=DEFAULT_CADENCE_S,
        help=f"Seconds of video time between sampled frames (default: {DEFAULT_CADENCE_S}).",
    )
    parser.add_argument(
        "--max-frames", type=int, default=None, help="Stop after N sampled frames."
    )
    parser.add_argument(
        "--context-text-n",
        type=int,
        default=DEFAULT_CONTEXT_TEXT_N,
        help=f"Recent captions to send with each request (default: {DEFAULT_CONTEXT_TEXT_N}).",
    )
    parser.add_argument(
        "--context-image-n",
        type=int,
        default=DEFAULT_CONTEXT_IMAGE_N,
        help=(
            "Recent JPEG frames to send with each request, giving the model a "
            "motion window across N+1 frames "
            f"(default: {DEFAULT_CONTEXT_IMAGE_N}; server auto-downscales when "
            "multiple images are present)."
        ),
    )
    parser.add_argument(
        "--system-prompt-file",
        type=Path,
        default=None,
        help="Path to a text file whose contents override the server's DEFAULT_SYSTEM_PROMPT.",
    )
    parser.add_argument(
        "--scene-cut-threshold",
        type=float,
        default=DEFAULT_SCENE_CUT_THRESHOLD,
        help=(
            "Bhattacharyya distance above which a sampled frame is treated as "
            "the start of a new scene; on detection both context windows are "
            f"cleared (default: {DEFAULT_SCENE_CUT_THRESHOLD}; set 0 to disable)."
        ),
    )
    parser.add_argument(
        "--session-out",
        type=Path,
        default=None,
        help=(
            "If set, append one JSON line per successful response to this "
            "path. The M3 viewer consumes this file."
        ),
    )
    args = parser.parse_args()

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        print(f"error: cannot open {args.video}", file=sys.stderr)
        return 1

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    stride = max(1, int(round(fps * args.cadence)))
    print(
        f"video fps={fps:.2f}  cadence={args.cadence}s  stride={stride} frames  "
        f"text_ctx={args.context_text_n}  image_ctx={args.context_image_n}  "
        f"scene_cut_thresh={args.scene_cut_threshold}",
        file=sys.stderr,
    )

    system_prompt_override: str | None = None
    if args.system_prompt_file is not None:
        system_prompt_override = args.system_prompt_file.read_text().strip()

    caption_window: deque[str] = deque(maxlen=max(args.context_text_n, 0))
    frame_window: deque[str] = deque(maxlen=max(args.context_image_n, 0))
    prev_sampled_frame: np.ndarray | None = None

    sampled = 0
    frame_idx = 0

    session_file = args.session_out.open("a") if args.session_out else None
    try:
        with httpx.Client(timeout=30.0) as client:
            while True:
                ok, frame = cap.read()
                if not ok:
                    break

                if frame_idx % stride == 0:
                    t_video = frame_idx / fps

                    if (
                        args.scene_cut_threshold > 0
                        and prev_sampled_frame is not None
                    ):
                        dist = hist_distance(prev_sampled_frame, frame)
                        if dist > args.scene_cut_threshold:
                            caption_window.clear()
                            frame_window.clear()
                            print(
                                f"[t={t_video:6.2f}s] -- scene cut (hist dist "
                                f"{dist:.2f} > {args.scene_cut_threshold:.2f}); "
                                f"context reset --",
                                file=sys.stderr,
                            )
                    prev_sampled_frame = frame

                    t_capture_start = time.perf_counter()
                    image_b64 = encode_frame_to_b64_jpeg(frame)
                    capture_ms = (time.perf_counter() - t_capture_start) * 1000.0

                    payload: dict = {
                        "image_b64": image_b64,
                        "recent_commentary": list(caption_window),
                        "recent_frames_b64": list(frame_window),
                    }
                    if system_prompt_override is not None:
                        payload["system_prompt"] = system_prompt_override

                    client_send_ts_ms = time.time() * 1000.0
                    payload["client_send_ts_ms"] = client_send_ts_ms

                    resp = client.post(args.url, json=payload)
                    client_recv_ts_ms = time.time() * 1000.0

                    if resp.status_code != 200:
                        print(
                            f"[t={t_video:6.2f}s] HTTP {resp.status_code}: {resp.text[:200]}"
                        )
                    else:
                        body = resp.json()
                        text = body["text"]
                        split = compute_timing_split(
                            client_send_ts_ms=client_send_ts_ms,
                            client_recv_ts_ms=client_recv_ts_ms,
                            server_recv_ts_ms=body["server_recv_ts_ms"],
                            server_send_ts_ms=body["server_send_ts_ms"],
                        )
                        print(
                            f'[t={t_video:6.2f}s] "{text}"  '
                            f"(cap={capture_ms:.0f}ms "
                            f"up={split['upload_ms']:.0f}ms "
                            f"inf={split['inference_ms']:.0f}ms "
                            f"down={split['download_ms']:.0f}ms "
                            f"e2e={split['e2e_ms']:.0f}ms)"
                        )

                        if session_file is not None:
                            entry = build_session_entry(
                                capture_t_s=t_video,
                                text=text,
                                capture_ms=capture_ms,
                                timing_split=split,
                                server_total_ms=body.get("server_total_ms", 0.0),
                                image_width=body.get("image_width", 0),
                                image_height=body.get("image_height", 0),
                            )
                            session_file.write(json.dumps(entry) + "\n")
                            session_file.flush()

                        caption_window.append(text)
                        if frame_window.maxlen and frame_window.maxlen > 0:
                            frame_window.append(image_b64)

                    sampled += 1
                    if args.max_frames is not None and sampled >= args.max_frames:
                        break

                frame_idx += 1
    finally:
        if session_file is not None:
            session_file.close()

    cap.release()
    print(f"done: sampled {sampled} frame(s) from {frame_idx} read.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
