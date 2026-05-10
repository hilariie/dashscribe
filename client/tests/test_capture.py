"""Tests for client/capture.py.

The load-bearing units:
  - JPEG encoder: produces base64 the server can decode.
  - Caption-window deque: drops oldest when full.
  - Timing-split math: maps four timestamps to upload/inference/download/e2e.
  - M3 session-entry builder: produces the JSONL row the viewer consumes.

The frame-stride math and HTTP loop are exercised end-to-end by the
integration test, not unit-tested here.
"""

import base64
import io
import json
from collections import deque

import numpy as np
import pytest
from PIL import Image

import capture


def _make_bgr_frame(width: int = 64, height: int = 48) -> np.ndarray:
    """OpenCV gives us BGR uint8 frames; mimic that here."""
    return np.full((height, width, 3), (200, 60, 120), dtype=np.uint8)


def test_encode_frame_round_trips_to_a_valid_image():
    frame = _make_bgr_frame(width=80, height=60)

    b64 = capture.encode_frame_to_b64_jpeg(frame)

    raw = base64.b64decode(b64, validate=True)
    img = Image.open(io.BytesIO(raw))
    img.verify()

    img = Image.open(io.BytesIO(raw))
    assert img.format == "JPEG"
    assert img.size == (80, 60)


def test_encode_frame_respects_quality_argument():
    frame = _make_bgr_frame()

    high = base64.b64decode(capture.encode_frame_to_b64_jpeg(frame, quality=95))
    low = base64.b64decode(capture.encode_frame_to_b64_jpeg(frame, quality=20))

    assert len(high) > len(low), "higher JPEG quality should produce a larger payload"


def test_encode_frame_rejects_garbage_input():
    with pytest.raises((RuntimeError, Exception)):
        capture.encode_frame_to_b64_jpeg(np.array(["not", "an", "image"]))


def test_caption_window_drops_oldest_when_full():
    """The sliding-window contract: pushing N+2 captions into a maxlen=N
    deque keeps only the last N, with the oldest two evicted in order."""
    window: deque[str] = deque(maxlen=4)
    for cap in ["one", "two", "three", "four", "five", "six"]:
        window.append(cap)

    assert list(window) == ["three", "four", "five", "six"]
    assert "one" not in window
    assert "two" not in window


def test_caption_window_zero_capacity_drops_everything():
    """--context-text-n=0 should mean 'send no recent commentary'."""
    window: deque[str] = deque(maxlen=0)
    window.append("anything")
    assert list(window) == []


def test_compute_timing_split_simple_case():
    """No clock skew, simple round-trip."""
    split = capture.compute_timing_split(
        client_send_ts_ms=1000.0,
        client_recv_ts_ms=3000.0,
        server_recv_ts_ms=1500.0,
        server_send_ts_ms=2500.0,
    )
    assert split["upload_ms"] == pytest.approx(500.0)
    assert split["inference_ms"] == pytest.approx(1000.0)
    assert split["download_ms"] == pytest.approx(500.0)
    assert split["e2e_ms"] == pytest.approx(2000.0)


def test_hist_distance_identical_frames_is_zero():
    """A frame compared against itself should yield Bhattacharyya distance 0."""
    frame = np.full((120, 160, 3), (140, 80, 200), dtype=np.uint8)
    assert capture.hist_distance(frame, frame) == pytest.approx(0.0, abs=1e-6)


def test_hist_distance_disjoint_frames_is_high():
    """Solid black vs solid white should land near 1.0 (disjoint distributions)."""
    black = np.zeros((120, 160, 3), dtype=np.uint8)
    white = np.full((120, 160, 3), 255, dtype=np.uint8)
    d = capture.hist_distance(black, white)
    assert d > 0.9, f"expected > 0.9 for disjoint frames, got {d}"


def test_hist_distance_overlapping_distributions_below_default_threshold():
    """A frame with small per-pixel noise should still land under the default
    scene-cut threshold; otherwise intra-scene motion would constantly trigger
    a false reset."""
    rng = np.random.default_rng(seed=42)
    base = rng.integers(80, 130, size=(120, 160, 3), dtype=np.uint8)
    perturbation = rng.integers(-3, 4, size=base.shape).astype(np.int16)
    noisy = np.clip(base.astype(np.int16) + perturbation, 0, 255).astype(np.uint8)

    d = capture.hist_distance(base, noisy)
    assert d < capture.DEFAULT_SCENE_CUT_THRESHOLD, (
        f"slight noise should not trip the cut threshold; got {d}"
    )


def test_compute_timing_split_with_negative_skew():
    """Server clock 200ms behind the client. Inference is server-internal so
    immune; upload + download still sum correctly even with biased components.
    """
    skew = -200.0
    client_send = 10_000.0
    client_recv = 12_000.0
    real_upload = 400.0
    real_inference = 1_200.0

    server_recv = client_send + real_upload + skew
    server_send = server_recv + real_inference

    split = capture.compute_timing_split(
        client_send_ts_ms=client_send,
        client_recv_ts_ms=client_recv,
        server_recv_ts_ms=server_recv,
        server_send_ts_ms=server_send,
    )

    assert split["inference_ms"] == pytest.approx(real_inference)
    assert split["e2e_ms"] == pytest.approx(client_recv - client_send)
    # Upload and download are individually skewed; their sum equals e2e - inference.
    assert split["upload_ms"] + split["download_ms"] == pytest.approx(
        split["e2e_ms"] - split["inference_ms"]
    )


# ---------- M3: session-entry builder (the JSONL row the viewer consumes) ----

_EXAMPLE_TIMING_SPLIT = {
    "upload_ms": 290.0,
    "inference_ms": 1180.0,
    "download_ms": 50.0,
    "e2e_ms": 1524.1,
}


def test_build_session_entry_has_all_schema_keys():
    """The viewer's TypeScript SessionEntry depends on every key being present.
    A missing key would silently degrade the UI (NaN HUD readouts, etc.)."""
    entry = capture.build_session_entry(
        capture_t_s=1.0,
        text="Lead car braking. Advice: brake now.",
        capture_ms=4.1,
        timing_split=_EXAMPLE_TIMING_SPLIT,
        server_total_ms=1183.0,
        image_width=1920,
        image_height=1080,
    )

    expected_keys = {
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
    }
    assert set(entry.keys()) == expected_keys


def test_build_session_entry_round_trips_through_json():
    """The recorder writes one JSON line per response. Round-tripping through
    json.dumps/json.loads must preserve every value within rounding."""
    entry = capture.build_session_entry(
        capture_t_s=2.5,
        text="Cyclist crossing right-to-left. Advice: slow down.",
        capture_ms=3.872,
        timing_split=_EXAMPLE_TIMING_SPLIT,
        server_total_ms=1183.0,
        image_width=1920,
        image_height=1080,
    )

    parsed = json.loads(json.dumps(entry))
    assert parsed["capture_t_s"] == pytest.approx(2.5)
    assert parsed["text"] == "Cyclist crossing right-to-left. Advice: slow down."
    assert parsed["capture_ms"] == pytest.approx(3.87, abs=1e-6)
    assert parsed["upload_ms"] == pytest.approx(290.0)
    assert parsed["inference_ms"] == pytest.approx(1180.0)
    assert parsed["e2e_ms"] == pytest.approx(1524.1)
    assert parsed["image_width"] == 1920
    assert parsed["image_height"] == 1080
