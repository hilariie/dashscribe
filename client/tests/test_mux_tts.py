"""Tests for mux_tts: argv construction. ffmpeg itself is not invoked here."""

from pathlib import Path

from mux_tts import build_ffmpeg_argv


def test_argv_no_existing_audio():
    argv = build_ffmpeg_argv(
        Path("v.mp4"),
        Path("t.mp3"),
        Path("o.mp4"),
        video_has_audio=False,
    )
    assert argv[0] == "ffmpeg"
    assert "-y" in argv
    # Two -i flags for the two inputs in the right order.
    i_indices = [i for i, a in enumerate(argv) if a == "-i"]
    assert len(i_indices) == 2
    assert argv[i_indices[0] + 1] == "v.mp4"
    assert argv[i_indices[1] + 1] == "t.mp3"
    # Video stream copied from input 0.
    assert "0:v" in argv
    # TTS audio mapped from input 1, encoded to AAC.
    assert "1:a" in argv
    assert "aac" in argv
    # No 0:a mapping when source had no audio.
    assert "0:a" not in argv
    # Output is the last element.
    assert argv[-1] == "o.mp4"


def test_argv_with_existing_audio_preserves_both():
    argv = build_ffmpeg_argv(
        Path("v.mp4"),
        Path("t.mp3"),
        Path("o.mp4"),
        video_has_audio=True,
    )
    # Source audio preserved (copied) AND TTS appended as second audio (AAC).
    assert "0:a" in argv
    assert "1:a" in argv
    # Codec assignments are stream-specific so 0:a copies and 1:a encodes.
    assert "-c:a:0" in argv
    copy_idx = argv.index("-c:a:0")
    assert argv[copy_idx + 1] == "copy"
    assert "-c:a:1" in argv
    enc_idx = argv.index("-c:a:1")
    assert argv[enc_idx + 1] == "aac"
    # Video still copied.
    assert "copy" in argv
    assert argv[-1] == "o.mp4"
