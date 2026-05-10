"""Tests for build_messages, prompt defaults, and multi-image downscale in
server-mirror.py.

These tests construct messages and resize images without loading the model —
the units under test are prompt-assembly logic and the multi-image-resolution
policy, both of which determine what every dashcam frame gets shown alongside.
"""

from PIL import Image


def _user_turn(messages):
    return next(m for m in messages if m["role"] == "user")


def _system_text(messages):
    sys_msg = next(m for m in messages if m["role"] == "system")
    return sys_msg["content"][0]["text"]


def test_default_system_prompt_is_non_empty(server_mirror):
    s = server_mirror.DEFAULT_SYSTEM_PROMPT
    assert isinstance(s, str)
    assert len(s.strip()) > 0
    # Guard against unfilled template placeholders sneaking in.
    assert "{" not in s and "}" not in s


def test_default_system_prompt_locks_advice_format(server_mirror):
    """The co-pilot mode requires the model to produce '<observation>. Advice: <action>.'"""
    s = server_mirror.DEFAULT_SYSTEM_PROMPT
    assert "Advice" in s


def test_default_system_prompt_acknowledges_multi_frame_motion(server_mirror):
    """The prompt must explicitly tell the model that multiple frames carry
    temporal information, otherwise it treats each as an independent still."""
    s = server_mirror.DEFAULT_SYSTEM_PROMPT.lower()
    assert "motion" in s or "sequential" in s or "across" in s


def test_build_messages_returns_qwen2vl_chat_shape(server_mirror):
    msgs = server_mirror.build_messages(
        image_present=True,
        recent_commentary=[],
        recent_frames_b64=[],
        system_prompt=None,
        user_prompt="Caption this frame.",
    )
    assert isinstance(msgs, list)
    assert all("role" in m and "content" in m for m in msgs)
    assert msgs[0]["role"] == "system"
    assert msgs[-1]["role"] == "user"


def test_build_messages_always_includes_current_image(server_mirror):
    msgs = server_mirror.build_messages(
        image_present=True,
        recent_commentary=["earlier caption"],
        recent_frames_b64=[],
        system_prompt=None,
        user_prompt="Caption this frame.",
    )
    user_content = _user_turn(msgs)["content"]
    image_count = sum(1 for c in user_content if c["type"] == "image")
    assert image_count == 1


def test_build_messages_caps_recent_commentary(server_mirror):
    cap = server_mirror.MAX_TEXT_CTX
    # Use unique non-substring tokens so "caption 1" doesn't match "caption 10".
    long_history = [f"CAP-{i:03d}-XYZ" for i in range(cap + 5)]

    msgs = server_mirror.build_messages(
        image_present=True,
        recent_commentary=long_history,
        recent_frames_b64=[],
        system_prompt=None,
        user_prompt="Caption this frame.",
    )
    sys_text = _system_text(msgs)

    for kept in long_history[-cap:]:
        assert kept in sys_text
    for dropped in long_history[: len(long_history) - cap]:
        assert dropped not in sys_text


def test_build_messages_caps_recent_frames(server_mirror):
    cap = server_mirror.MAX_IMAGE_CTX
    too_many = ["fake-b64"] * (cap + 3)

    msgs = server_mirror.build_messages(
        image_present=True,
        recent_commentary=[],
        recent_frames_b64=too_many,
        system_prompt=None,
        user_prompt="Caption this frame.",
    )
    user_content = _user_turn(msgs)["content"]
    image_count = sum(1 for c in user_content if c["type"] == "image")
    # cap prior frames + 1 current frame
    assert image_count == cap + 1


def test_build_messages_honours_system_prompt_override(server_mirror):
    custom = "OVERRIDE-SYSTEM-PROMPT-XYZ"
    msgs = server_mirror.build_messages(
        image_present=True,
        recent_commentary=[],
        recent_frames_b64=[],
        system_prompt=custom,
        user_prompt="Caption this frame.",
    )
    sys_text = _system_text(msgs)
    assert custom in sys_text
    assert server_mirror.DEFAULT_SYSTEM_PROMPT not in sys_text


def test_build_messages_user_prompt_appears_last(server_mirror):
    msgs = server_mirror.build_messages(
        image_present=True,
        recent_commentary=[],
        recent_frames_b64=[],
        system_prompt=None,
        user_prompt="UNIQUE-USER-PROMPT-XYZ",
    )
    user_content = _user_turn(msgs)["content"]
    text_parts = [c for c in user_content if c["type"] == "text"]
    assert len(text_parts) == 1
    assert text_parts[0]["text"] == "UNIQUE-USER-PROMPT-XYZ"
    assert user_content[-1]["type"] == "text"


def test_maybe_downscale_single_image_keeps_native_resolution(server_mirror):
    img = Image.new("RGB", (1920, 1080), color=(0, 0, 0))
    out = server_mirror.maybe_downscale_for_multi_image([img])
    assert len(out) == 1
    assert out[0].size == (1920, 1080)


def test_maybe_downscale_multi_image_resizes_each(server_mirror):
    cap = server_mirror.MULTI_IMAGE_MAX_SIDE
    big = Image.new("RGB", (1920, 1080), color=(0, 0, 0))
    smaller = Image.new("RGB", (320, 240), color=(0, 0, 0))
    out = server_mirror.maybe_downscale_for_multi_image([big, big, smaller])

    assert len(out) == 3
    for img in out:
        assert max(img.width, img.height) <= cap
    # Aspect ratio of the big frames should be preserved (16:9).
    assert abs((out[0].width / out[0].height) - (1920 / 1080)) < 0.02
    # The already-small image should be untouched.
    assert out[2].size == (320, 240)


def test_maybe_downscale_empty_list_is_safe(server_mirror):
    assert server_mirror.maybe_downscale_for_multi_image([]) == []
