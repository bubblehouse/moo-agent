"""
Tests for moo/agent/brain_state.py — BrainState dataclass.

BrainState is a plain mutable dataclass. These tests pin the default values
and confirm that each session field is independently mutable without any
cross-field side effects (mutable defaults use field(default_factory=...)).
"""

from moo.agent.brain.state import BrainState


def test_defaults_are_empty():
    s = BrainState()
    assert s.current_goal == ""
    assert s.current_plan == []
    assert s.plan_from_disk is False
    assert s.plan_exhausted is False
    assert s.session_done is False
    assert s.pending_done_msg == ""
    assert s.memory_summary == ""
    assert not s.rooms_built
    assert s.idle_wakeup_count == 0
    assert s.goal_only_count == 0
    assert s.foreman_paged is False
    assert s.token_dispatched_at is None
    assert s.token_dispatched_to is None
    assert s.prior_goal_for_reconnect == ""


def test_list_defaults_are_not_shared():
    """field(default_factory=list) must give each instance its own list."""
    a = BrainState()
    b = BrainState()
    a.current_plan.append("go north")
    a.rooms_built.append("The Library")
    assert b.current_plan == []
    assert not b.rooms_built


def test_constructor_sets_provided_fields():
    s = BrainState(
        current_goal="build the library",
        memory_summary="prior summary",
        prior_goal_for_reconnect="explore",
    )
    assert s.current_goal == "build the library"
    assert s.memory_summary == "prior summary"
    assert s.prior_goal_for_reconnect == "explore"
    # Other fields keep defaults
    assert s.current_plan == []
    assert s.session_done is False


def test_fields_are_independently_mutable():
    s = BrainState()
    s.current_goal = "find key"
    s.current_plan = ["go north", "look"]
    s.plan_exhausted = True
    s.session_done = True
    s.foreman_paged = True
    s.idle_wakeup_count = 5
    s.token_dispatched_at = 1234.5
    s.token_dispatched_to = "mason"

    assert s.current_goal == "find key"
    assert s.current_plan == ["go north", "look"]
    assert s.plan_exhausted is True
    assert s.session_done is True
    assert s.foreman_paged is True
    assert s.idle_wakeup_count == 5
    assert s.token_dispatched_at == 1234.5
    assert s.token_dispatched_to == "mason"
