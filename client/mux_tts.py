"""ffmpeg wrapper that combines a source video with a TTS audio file.

Produces an MP4 with the source video (stream-copied) plus the TTS as a
second audio track. If the source video already has an audio stream (e.g.
after the YouTube-ambient re-attach), it's preserved so the output has two
audio tracks the user can mix in post.

    cd client
    uv run python mux_tts.py \\
        --video ../data/video1.mp4 \\
        --tts   ../data/session-video1.tts.mp3 \\
        --out   ../data/video1_narrated.mp4
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


def has_audio_stream(video_path: Path) -> bool:
    """True iff ffprobe reports at least one audio stream on the input."""
    out = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_streams",
            "-select_streams",
            "a",
            str(video_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return bool(json.loads(out.stdout).get("streams"))


def build_ffmpeg_argv(
    video: Path, tts: Path, out: Path, *, video_has_audio: bool
) -> list[str]:
    """Construct the ffmpeg argv. Pure function, no I/O — testable."""
    argv: list[str] = [
        "ffmpeg",
        "-y",
        "-i",
        str(video),
        "-i",
        str(tts),
        "-map",
        "0:v",
        "-c:v",
        "copy",
    ]
    if video_has_audio:
        # Preserve original audio (typically the YouTube ambient re-attach) and
        # add the TTS as a second audio stream.
        argv += [
            "-map",
            "0:a",
            "-c:a:0",
            "copy",
            "-map",
            "1:a",
            "-c:a:1",
            "aac",
        ]
    else:
        argv += [
            "-map",
            "1:a",
            "-c:a",
            "aac",
        ]
    argv.append(str(out))
    return argv


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Mux a TTS audio file with a source video into an MP4."
    )
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--tts", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        print("error: ffmpeg/ffprobe not found on PATH.", file=sys.stderr)
        return 2
    if not args.video.exists():
        print(f"error: video not found: {args.video}", file=sys.stderr)
        return 2
    if not args.tts.exists():
        print(f"error: tts not found: {args.tts}", file=sys.stderr)
        return 2

    video_has_audio = has_audio_stream(args.video)
    argv = build_ffmpeg_argv(
        args.video, args.tts, args.out, video_has_audio=video_has_audio
    )
    print(" ".join(argv), file=sys.stderr)
    proc = subprocess.run(argv, check=False)
    if proc.returncode != 0:
        print(f"ffmpeg failed with exit code {proc.returncode}", file=sys.stderr)
        return proc.returncode
    print(f"wrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
