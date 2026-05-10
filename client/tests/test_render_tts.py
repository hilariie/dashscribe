"""Tests for render_tts: selection rule and silence-padded stitching.

Skips the actual kokoro model load — `synth` is the seam, and we hand
in deterministic stubs.
"""

import json
from pathlib import Path

import numpy as np
import pytest

import render_tts
from render_tts import (
    SAMPLE_RATE,
    derive_default_out,
    parse_jsonl,
    select_urgent_blocks,
    stitch,
)


def _entry(t: float, text: str) -> dict:
    return {
        "capture_t_s": t,
        "text": text,
        "capture_ms": 0,
        "upload_ms": 0,
        "inference_ms": 0,
        "download_ms": 0,
        "e2e_ms": 0,
        "server_total_ms": 0,
        "image_width": 0,
        "image_height": 0,
    }


class TestSelectUrgentBlocks:
    def test_filters_calm_and_cautious_out(self):
        entries = [
            _entry(0, "Empty road. Advice: maintain speed."),
            _entry(3, "Pedestrian on sidewalk. Advice: slow down."),
            _entry(6, "Lead car braking hard. Advice: brake now."),
        ]
        blocks = select_urgent_blocks(entries)
        assert len(blocks) == 1
        assert "brake now" in blocks[0].text

    def test_no_urgent_returns_empty(self):
        entries = [_entry(0, "Empty road. Advice: maintain speed.")]
        assert select_urgent_blocks(entries) == []

    def test_collision_keyword_passes_through_when_advice_is_urgent(self):
        # Display-track will preempt; urgent-class block emerges.
        entries = [
            _entry(0, "Quiet road. Advice: maintain."),
            _entry(1, "Collision imminent. Advice: brake now."),
        ]
        blocks = select_urgent_blocks(entries)
        assert len(blocks) == 1


def _tone_synth(samples: int, value: float = 1.0):
    """Return a synth that always emits a clip of `samples` samples filled with `value`."""

    def synth(_text: str) -> tuple[np.ndarray, int]:
        return np.full(samples, value, dtype=np.float32), SAMPLE_RATE

    return synth


class TestStitch:
    def test_empty_blocks_returns_silent_buffer(self):
        master = stitch([], _tone_synth(100), total_duration_s=2.0)
        assert master.shape == (int(round(2.0 * SAMPLE_RATE)),)
        assert master.dtype == np.float32
        assert np.allclose(master, 0.0)

    def test_places_clip_at_start_time(self):
        # One urgent block at t=10s; clip is 1s long; check the buffer has
        # silence before t=10 and the clip starts exactly at 10s.
        entries = [_entry(10, "Lead car. Advice: brake now.")]
        blocks = select_urgent_blocks(entries)
        clip_samples = SAMPLE_RATE  # 1 second
        synth = _tone_synth(clip_samples)
        master = stitch(blocks, synth, total_duration_s=20.0)

        offset = 10 * SAMPLE_RATE
        assert np.allclose(master[: offset], 0.0)
        assert np.allclose(master[offset : offset + clip_samples], 1.0)
        assert np.allclose(master[offset + clip_samples :], 0.0)

    def test_truncates_clip_at_next_block_start(self):
        # Two urgent blocks 0.5s apart; each clip is 1.0s long. The first
        # clip must be truncated at the second block's start.
        entries = [
            _entry(10.0, "Lead car. Advice: brake now."),
            _entry(10.5, "Vehicle stopped. Advice: brake now."),
        ]
        # Force two blocks via separate observations + advice change keywords.
        # build_display_track preempt logic: second matches via observation
        # keyword `stopped`? No — we need actual escalation. Build manually:
        from lib.display_track import DisplayBlock

        blocks = [
            DisplayBlock(
                start_time=10.0,
                end_time=10.5,
                text="A. Advice: brake now.",
                source_entry=entries[0],
                was_preempted=False,
            ),
            DisplayBlock(
                start_time=10.5,
                end_time=float("inf"),
                text="B. Advice: brake hard.",
                source_entry=entries[1],
                was_preempted=True,
            ),
        ]
        clip_samples = SAMPLE_RATE  # 1.0s
        synth = _tone_synth(clip_samples, value=1.0)
        master = stitch(blocks, synth, total_duration_s=15.0)

        first_start = int(round(10.0 * SAMPLE_RATE))
        second_start = int(round(10.5 * SAMPLE_RATE))
        # First clip: from first_start to second_start (0.5s of tone, then truncated)
        assert np.all(master[first_start:second_start] == 1.0)
        # Second clip: full 1s of tone starting at second_start
        assert np.all(master[second_start : second_start + clip_samples] == 1.0)

    def test_clip_truncated_at_buffer_end(self):
        entries = [_entry(9.5, "X. Advice: brake.")]
        blocks = select_urgent_blocks(entries)
        clip_samples = 2 * SAMPLE_RATE  # 2s clip but only 0.5s left in buffer
        synth = _tone_synth(clip_samples)
        master = stitch(blocks, synth, total_duration_s=10.0)

        offset = int(round(9.5 * SAMPLE_RATE))
        n_total = 10 * SAMPLE_RATE
        # Tone fills the rest of the buffer
        assert np.all(master[offset:n_total] == 1.0)
        assert master.shape == (n_total,)

    def test_synth_sample_rate_mismatch_raises(self):
        entries = [_entry(0, "X. Advice: brake.")]
        blocks = select_urgent_blocks(entries)

        def bad_synth(_t):
            return np.zeros(100, dtype=np.float32), 16000

        with pytest.raises(RuntimeError, match="sample rate"):
            stitch(blocks, bad_synth, total_duration_s=5.0)


class TestParseJsonl:
    def test_parses_well_formed(self, tmp_path: Path):
        p = tmp_path / "s.jsonl"
        p.write_text(
            "\n".join(
                [
                    json.dumps(_entry(0, "A. Advice: maintain.")),
                    json.dumps(_entry(1, "B. Advice: brake.")),
                    "",
                ]
            )
        )
        entries = parse_jsonl(p)
        assert len(entries) == 2
        assert entries[1]["text"].endswith("brake.")

    def test_raises_on_bad_json(self, tmp_path: Path):
        p = tmp_path / "s.jsonl"
        p.write_text("{not json}\n")
        with pytest.raises(ValueError, match="line 1"):
            parse_jsonl(p)


class TestDeriveDefaultOut:
    def test_replaces_jsonl_with_tts_mp3(self):
        out = derive_default_out(Path("/x/y/session-video1.jsonl"))
        assert out == Path("/x/y/session-video1.tts.mp3")

    def test_handles_no_extension(self):
        out = derive_default_out(Path("/x/y/session"))
        assert out == Path("/x/y/session.tts.mp3")
