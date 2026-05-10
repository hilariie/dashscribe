from lib.spoken_text import for_speech


def test_strips_advice_marker():
    assert (
        for_speech("Lead car braking. Advice: brake now.")
        == "Lead car braking. brake now."
    )


def test_no_advice_passes_through():
    assert for_speech("Clear road, nothing to do.") == "Clear road, nothing to do."


def test_case_insensitive():
    assert for_speech("X. ADVICE: hold lane.") == "X. hold lane."


def test_collapses_surrounding_whitespace():
    assert for_speech("X.   Advice:    brake.") == "X. brake."


def test_strips_only_first_occurrence():
    # 'Advice' inside an observation (rare but possible) shouldn't be silently
    # eaten beyond the first hit.
    assert (
        for_speech("Advice: stop. Advice: also stop.")
        == "stop. Advice: also stop."
    )


def test_strips_leading_and_trailing_whitespace():
    assert for_speech("   Advice: hold.   ") == "hold."
