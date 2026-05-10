"""Caption -> spoken-text transformation.

The locked M2 prompt format is "<observation>. Advice: <action>." — fine for
on-screen subtitles, but the literal word "Advice:" reads awkwardly when
spoken aloud. for_speech() drops the marker and tightens whitespace so the
narrator says "Lead car braking. brake now." instead of
"Lead car braking. Advice: brake now."
"""

import re

# Match 'Advice:' (case-insensitive) plus any surrounding whitespace, so the
# replacement collapses what would otherwise be a stuttering pause.
_ADVICE_RE = re.compile(r"\s*advice:\s*", flags=re.IGNORECASE)


def for_speech(text: str) -> str:
    return _ADVICE_RE.sub(" ", text, count=1).strip()
