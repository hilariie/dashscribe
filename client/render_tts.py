"""M4 TTS renderer.

Reads a session JSONL, builds the same display track the viewer uses, filters
to urgent-only blocks (brake / stop / swerve / collision / crash), synthesises
each via kokoro-onnx, and writes a single MP3 timed against ``capture_t_s``
next to the JSONL. The viewer auto-discovers the sibling file and plays it in
sync with the video.

    cd client
    uv run python render_tts.py --session ../data/session-video1.jsonl

The first run downloads ~330 MB of kokoro model weights into
``data/models/kokoro/`` (gitignored). Subsequent runs reuse them.
"""

import argparse
import json
import math
import sys
import urllib.request
from collections.abc import Callable
from pathlib import Path

import numpy as np

from lib.display_track import DisplayBlock, build_display_track
from lib.spoken_text import for_speech
from lib.urgency import classify_advice

DEFAULT_VOICE = "af_heart"
DEFAULT_SPEED = 1.0
SAMPLE_RATE = 24000  # kokoro-onnx output rate
TAIL_PADDING_S = 5.0  # silence after the last entry so the buffer doesn't truncate

REPO_ROOT = Path(__file__).resolve().parent.parent
MODEL_DIR = REPO_ROOT / "data" / "models" / "kokoro"
MODEL_URL = (
    "https://github.com/thewh1teagle/kokoro-onnx/releases/download/"
    "model-files-v1.0/kokoro-v1.0.onnx"
)
VOICES_URL = (
    "https://github.com/thewh1teagle/kokoro-onnx/releases/download/"
    "model-files-v1.0/voices-v1.0.bin"
)


def parse_jsonl(path: Path) -> list[dict]:
    entries: list[dict] = []
    for i, line in enumerate(path.read_text().splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError as e:
            raise ValueError(f"line {i}: {e}") from e
    return entries


def select_urgent_blocks(entries: list[dict]) -> list[DisplayBlock]:
    """Display-track blocks where the advice classifies as urgent.

    Cautious and calm blocks stay silent.
    """
    track = build_display_track(entries)
    return [b for b in track if classify_advice(b.text) == "urgent"]


def stitch(
    blocks: list[DisplayBlock],
    synth: Callable[[str], tuple[np.ndarray, int]],
    total_duration_s: float,
) -> np.ndarray:
    """Place each block's TTS clip at block.start_time on a master buffer.

    Overlap policy: if a clip would run into the next block's start, it is
    truncated at that boundary. The urgent stream is sparse so this rarely
    matters; truncating beats overlap.
    """
    n_total = max(0, int(math.ceil(total_duration_s * SAMPLE_RATE)))
    master = np.zeros(n_total, dtype=np.float32)
    if not blocks:
        return master
    next_start_samples = [int(round(b.start_time * SAMPLE_RATE)) for b in blocks]
    next_start_samples.append(n_total)  # sentinel
    for i, block in enumerate(blocks):
        spoken = for_speech(block.text)
        clip, sr = synth(spoken)
        if sr != SAMPLE_RATE:
            raise RuntimeError(
                f"synth returned sample rate {sr}, expected {SAMPLE_RATE}"
            )
        start = next_start_samples[i]
        next_start = next_start_samples[i + 1]
        write_len = min(
            len(clip), max(0, next_start - start), max(0, n_total - start)
        )
        if write_len > 0:
            master[start : start + write_len] = clip[:write_len].astype(np.float32)
    return master


def derive_default_out(session_path: Path) -> Path:
    return session_path.parent / (session_path.stem + ".tts.mp3")


def _ensure_model_files() -> tuple[Path, Path]:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    model_path = MODEL_DIR / "kokoro-v1.0.onnx"
    voices_path = MODEL_DIR / "voices-v1.0.bin"
    for url, dst in ((MODEL_URL, model_path), (VOICES_URL, voices_path)):
        if not dst.exists():
            print(f"downloading {url} -> {dst}", file=sys.stderr)
            urllib.request.urlretrieve(url, dst)
    return model_path, voices_path


def _load_kokoro_synth(voice: str, speed: float):
    """Lazy-load kokoro and return a callable matching the synth contract."""
    from kokoro_onnx import Kokoro

    model_path, voices_path = _ensure_model_files()
    kokoro = Kokoro(str(model_path), str(voices_path))

    def synth(text: str) -> tuple[np.ndarray, int]:
        return kokoro.create(text, voice=voice, speed=speed)

    return synth


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render TTS narration for a session JSONL."
    )
    parser.add_argument(
        "--session", type=Path, required=True, help="Path to the session JSONL."
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output MP3 path. Defaults to <session-stem>.tts.mp3 alongside the JSONL.",
    )
    parser.add_argument("--voice", default=DEFAULT_VOICE)
    parser.add_argument("--speed", type=float, default=DEFAULT_SPEED)
    parser.add_argument(
        "--total-duration-s",
        type=float,
        default=None,
        help=(
            "Override the master buffer length (default: end of last entry "
            f"+ {TAIL_PADDING_S:.1f}s)."
        ),
    )
    args = parser.parse_args()

    entries = parse_jsonl(args.session)
    blocks = select_urgent_blocks(entries)
    print(
        f"selected {len(blocks)} urgent block(s) of {len(entries)} entries",
        file=sys.stderr,
    )

    if args.total_duration_s is not None:
        total_duration_s = args.total_duration_s
    elif entries:
        total_duration_s = entries[-1]["capture_t_s"] + TAIL_PADDING_S
    else:
        total_duration_s = 0.0

    synth = _load_kokoro_synth(args.voice, args.speed)
    master = stitch(blocks, synth, total_duration_s)

    out_path = args.out or derive_default_out(args.session)

    import soundfile as sf

    sf.write(str(out_path), master, SAMPLE_RATE, format="MP3")
    print(
        f"wrote {out_path} ({len(master) / SAMPLE_RATE:.1f}s @ {SAMPLE_RATE} Hz)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
