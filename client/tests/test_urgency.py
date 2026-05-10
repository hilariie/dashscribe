"""Mirrors viewer/src/lib/urgency.test.ts. Drift between the two is a bug."""

from lib.urgency import (
    classify_advice,
    contains_urgency_keyword,
    escalates,
    split_observation_advice,
)


class TestSplitObservationAdvice:
    def test_splits_on_advice_literal(self):
        obs, adv = split_observation_advice("Lead car braking. Advice: brake now.")
        assert obs == "lead car braking."
        assert adv == "brake now."

    def test_no_advice_returns_observation_only(self):
        obs, adv = split_observation_advice("clear road, nothing to do")
        assert obs == "clear road, nothing to do"
        assert adv == ""

    def test_case_insensitive_marker(self):
        _, adv = split_observation_advice("X. ADVICE: hold lane.")
        assert adv == "hold lane."


class TestClassifyAdvice:
    def test_calm_verbs(self):
        assert classify_advice("Foo. Advice: maintain speed.") == "calm"
        assert classify_advice("Foo. Advice: hold lane.") == "calm"
        assert classify_advice("Foo. Advice: continue.") == "calm"

    def test_urgent_verbs(self):
        assert classify_advice("Foo. Advice: brake now.") == "urgent"
        assert classify_advice("Foo. Advice: brake hard.") == "urgent"
        assert classify_advice("Foo. Advice: swerve right.") == "urgent"
        assert classify_advice("Foo. Advice: emergency stop.") == "urgent"

    def test_cautious_phrases_match_before_urgent_stop(self):
        # The bare 'stop' substring would match urgent if order were wrong;
        # this guards the lookup-order invariant.
        assert classify_advice("Foo. Advice: prepare to stop.") == "cautious"
        assert classify_advice("Foo. Advice: slow down.") == "cautious"

    def test_tolerates_whitespace_and_case(self):
        assert classify_advice("  FOO.   ADVICE:    BRAKE NOW.   ") == "urgent"

    def test_no_advice_clause_is_calm(self):
        assert classify_advice("just a fragment, no advice") == "calm"


class TestContainsUrgencyKeyword:
    def test_collision(self):
        assert contains_urgency_keyword("Collision imminent ahead.") is True

    def test_closing_in_multi_word(self):
        assert contains_urgency_keyword("Vehicle closing in fast.") is True

    def test_calm_observation(self):
        assert contains_urgency_keyword("Empty highway, clear conditions.") is False

    def test_case_insensitive(self):
        assert contains_urgency_keyword("CRASH ahead!") is True


class TestEscalates:
    def test_calm_to_urgent(self):
        assert escalates("calm", "urgent") is True

    def test_calm_to_cautious(self):
        assert escalates("calm", "cautious") is True

    def test_cautious_to_urgent(self):
        assert escalates("cautious", "urgent") is True

    def test_urgent_to_urgent_does_not_escalate(self):
        # No chained preempts.
        assert escalates("urgent", "urgent") is False

    def test_urgent_to_calm_does_not_escalate(self):
        # Don't preempt downwards.
        assert escalates("urgent", "calm") is False

    def test_calm_to_calm(self):
        assert escalates("calm", "calm") is False
