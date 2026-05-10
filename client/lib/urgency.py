"""Python port of viewer/src/lib/urgency.ts.

Source-of-truth for urgency-related lexicons. Mirrors the TS classifier
exactly so the M4 TTS renderer fires on the same blocks the viewer would
flash amber on. Lookup order matters: cautious phrases (e.g. "prepare to
stop") are matched before the urgent `stop` substring, otherwise they would
misclassify.
"""

from typing import Literal

AdviceClass = Literal["calm", "cautious", "urgent"]

# Order matters in the cautious list: longer/more-specific phrases first so
# "prepare to stop" is matched as cautious before "stop" classifies it as urgent.
CAUTIOUS_VERBS: tuple[str, ...] = ("slow down", "prepare to stop", "watch", "ease")
URGENT_VERBS: tuple[str, ...] = ("brake", "stop", "swerve", "evade", "emergency")
CALM_VERBS: tuple[str, ...] = ("maintain", "hold", "continue")
OBSERVATION_KEYWORDS: tuple[str, ...] = (
    "collision",
    "crash",
    "impact",
    "debris",
    "closing in",
    "imminent",
    "swerve",
)

_CLASS_RANK: dict[AdviceClass, int] = {"calm": 0, "cautious": 1, "urgent": 2}


def split_observation_advice(text: str) -> tuple[str, str]:
    """Return (observation, advice) split on the literal 'Advice:' marker.

    Both halves are lowercase-trimmed. Returns ('', '') compatible — observation
    falls back to the full text and advice is '' when no marker is present.
    """
    idx = text.lower().find("advice:")
    if idx == -1:
        return text.lower().strip(), ""
    observation = text[:idx].lower().strip()
    advice = text[idx + len("advice:") :].lower().strip()
    return observation, advice


def classify_advice(text: str) -> AdviceClass:
    _, advice = split_observation_advice(text)
    if advice == "":
        return "calm"
    for phrase in CAUTIOUS_VERBS:
        if phrase in advice:
            return "cautious"
    for phrase in URGENT_VERBS:
        if phrase in advice:
            return "urgent"
    for phrase in CALM_VERBS:
        if phrase in advice:
            return "calm"
    return "calm"


def contains_urgency_keyword(text: str) -> bool:
    lower = text.lower()
    return any(kw in lower for kw in OBSERVATION_KEYWORDS)


def escalates(prev: AdviceClass, nxt: AdviceClass) -> bool:
    return _CLASS_RANK[nxt] > _CLASS_RANK[prev]
