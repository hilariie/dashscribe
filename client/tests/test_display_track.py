"""Mirrors viewer/src/lib/displayTrack.test.ts. Drift is a bug."""

import math

from lib.display_track import build_display_track

MIN_DWELL_S = 2.5  # matches DEFAULT_MIN_DWELL_MS / 1000


def _entry(capture_t_s: float, text: str) -> dict:
    return {
        "capture_t_s": capture_t_s,
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


def _calm(t: float, suffix: str = "") -> dict:
    return _entry(
        t, f"Empty road, clear conditions{suffix}. Advice: maintain speed."
    )


def _calm_alt(t: float) -> dict:
    return _entry(t, "Highway flowing smoothly, no traffic. Advice: maintain speed.")


def _cautious(t: float) -> dict:
    return _entry(t, "Pedestrians on sidewalk ahead. Advice: slow down.")


def _urgent(t: float) -> dict:
    return _entry(t, "Lead car braking hard. Advice: brake now.")


def _urgent_b(t: float) -> dict:
    return _entry(t, "Vehicle stopped ahead. Advice: brake now.")


def _collision(t: float) -> dict:
    return _entry(t, "Collision imminent ahead. Advice: brake now.")


class TestBasics:
    def test_empty_input(self):
        assert build_display_track([]) == []

    def test_single_block_endtime_infinity(self):
        track = build_display_track([_calm(0)])
        assert len(track) == 1
        assert track[0].start_time == 0
        assert track[0].end_time == math.inf
        assert track[0].was_preempted is False


class TestDwellAndSimilarity:
    def test_drops_inside_dwell_when_no_urgency(self):
        track = build_display_track([_calm(0), _calm(1)])
        assert len(track) == 1
        assert track[0].source_entry["capture_t_s"] == 0

    def test_extends_past_dwell_when_similar(self):
        track = build_display_track([_calm(0), _calm(MIN_DWELL_S + 0.1)])
        assert len(track) == 1

    def test_opens_new_block_past_dwell_on_observation_change(self):
        track = build_display_track([_calm(0), _calm_alt(MIN_DWELL_S + 0.1)])
        assert len(track) == 2
        assert track[1].source_entry["capture_t_s"] == MIN_DWELL_S + 0.1
        assert track[0].end_time == MIN_DWELL_S + 0.1
        assert track[1].was_preempted is False

    def test_opens_new_block_past_dwell_when_advice_changes(self):
        track = build_display_track([_calm(0), _cautious(MIN_DWELL_S + 0.1)])
        assert len(track) == 2
        assert "slow down" in track[1].text


class TestPreempt:
    def test_preempts_inside_dwell_on_calm_to_urgent(self):
        track = build_display_track([_calm(0), _urgent(1)])
        assert len(track) == 2
        assert track[0].end_time == 1
        assert track[1].start_time == 1
        assert track[1].was_preempted is True

    def test_preempts_when_observation_gains_urgency_keyword(self):
        calm_brake = _entry(0, "Lead car slowing. Advice: brake.")
        collision_brake = _entry(1, "Collision imminent. Advice: brake now.")
        track = build_display_track([calm_brake, collision_brake])
        assert len(track) == 2
        assert track[1].was_preempted is True

    def test_no_chained_preempts(self):
        # Two urgents inside dwell — no further escalation possible and no new
        # urgency keyword. Should not open a new block.
        track = build_display_track([_urgent(0), _urgent_b(1)])
        assert len(track) == 1

    def test_preempt_pin_blocks_subsequent_dwell_calm(self):
        track = build_display_track([_calm(0), _urgent(1), _calm(2)])
        assert len(track) == 2
        assert "brake now" in track[1].text
        assert track[1].was_preempted is True
        assert track[1].end_time == math.inf

    def test_urgency_keyword_past_dwell_opens_non_preempt_block(self):
        track = build_display_track([_calm(0), _collision(MIN_DWELL_S + 0.1)])
        assert len(track) == 2
        assert track[1].was_preempted is False
