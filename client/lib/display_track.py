"""Python port of viewer/src/lib/displayTrack.ts.

Builds the same dwell + similarity + preempt schedule the viewer uses.
The TTS renderer consumes this so it speaks against the same blocks the
viewer flashes amber on. Drift between this file and displayTrack.ts is a
bug; tests in test_display_track.py mirror the TS test suite.
"""

import math
import re
from dataclasses import dataclass
from typing import Any

from .urgency import (
    classify_advice,
    contains_urgency_keyword,
    escalates,
    split_observation_advice,
)

DEFAULT_MIN_DWELL_MS = 2500
DEFAULT_JACCARD_THRESHOLD = 0.5

_TOKEN_PUNCT_RE = re.compile(r"[^\w\s]", flags=re.UNICODE)


@dataclass
class DisplayBlock:
    start_time: float
    end_time: float  # math.inf for the last block
    text: str
    source_entry: dict[str, Any]
    was_preempted: bool


def _tokenise(observation: str) -> set[str]:
    cleaned = _TOKEN_PUNCT_RE.sub(" ", observation.lower())
    return {w for w in cleaned.split() if len(w) > 2}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    intersection = len(a & b)
    union = len(a) + len(b) - intersection
    return 1.0 if union == 0 else intersection / union


def _meaningfully_different(
    prev: dict[str, Any], nxt: dict[str, Any], jaccard_threshold: float
) -> bool:
    prev_obs, prev_adv = split_observation_advice(prev["text"])
    nxt_obs, nxt_adv = split_observation_advice(nxt["text"])
    if prev_adv != nxt_adv:
        return True
    return _jaccard(_tokenise(prev_obs), _tokenise(nxt_obs)) < jaccard_threshold


def _should_preempt(current: dict[str, Any], candidate: dict[str, Any]) -> bool:
    current_class = classify_advice(current["text"])
    candidate_class = classify_advice(candidate["text"])
    if escalates(current_class, candidate_class):
        return True
    # Observation-keyword preempt fires only when the candidate has a keyword
    # the current displayed caption did not — sustained collisions don't cause
    # repeated preempts.
    return contains_urgency_keyword(candidate["text"]) and not contains_urgency_keyword(
        current["text"]
    )


def build_display_track(
    entries: list[dict[str, Any]],
    *,
    min_dwell_ms: int = DEFAULT_MIN_DWELL_MS,
    jaccard_threshold: float = DEFAULT_JACCARD_THRESHOLD,
) -> list[DisplayBlock]:
    """Build a display schedule from raw session entries.

    Assumes `entries` is sorted by `capture_t_s` ascending. Output blocks have
    non-overlapping [start_time, end_time) intervals; the last block has
    end_time = math.inf.
    """
    track: list[DisplayBlock] = []
    if not entries:
        return track

    min_dwell_s = min_dwell_ms / 1000.0

    def open_block(entry: dict[str, Any], was_preempted: bool) -> None:
        if track:
            track[-1].end_time = entry["capture_t_s"]
        track.append(
            DisplayBlock(
                start_time=entry["capture_t_s"],
                end_time=math.inf,
                text=entry["text"],
                source_entry=entry,
                was_preempted=was_preempted,
            )
        )

    for entry in entries:
        if not track:
            open_block(entry, was_preempted=False)
            continue
        current = track[-1]
        elapsed = entry["capture_t_s"] - current.start_time

        if elapsed < min_dwell_s:
            # Inside dwell. The only way to swap is a hard-preempt.
            if _should_preempt(current.source_entry, entry):
                open_block(entry, was_preempted=True)
            continue

        # Past dwell.
        if _meaningfully_different(current.source_entry, entry, jaccard_threshold):
            open_block(entry, was_preempted=False)
        # else: extend current block (no-op; end_time stays inf).

    return track
