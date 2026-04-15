"""
Tests for moo/agent/brain_prompt.py — pure string construction.

Both builders are pure functions with no Brain state. These tests pin the
exact shape of the output for each branch so we catch any drift when the
prompt preambles change.
"""

from moo.agent.brain.prompt import (
    PATCH_INSTRUCTIONS,
    PATCH_INSTRUCTIONS_TOOLS_ACTIVE,
    build_system_prompt,
    build_user_message,
)
from moo.agent.soul import Soul


def _soul(**overrides) -> Soul:
    defaults = dict(
        name="Tester",
        mission="Your mission is to test.",
        persona="You are a helpful test agent.",
        context="",
        addendum="",
        rules=[],
        verb_mappings=[],
        tools=[],
    )
    defaults.update(overrides)
    return Soul(**defaults)  # type: ignore[arg-type]


# --- build_system_prompt ---


def test_system_prompt_text_mode_has_mission_persona_patch_instructions():
    soul = _soul()
    out = build_system_prompt(soul, tools_active=False)
    assert "Your mission is to test." in out
    assert "You are a helpful test agent." in out
    assert PATCH_INSTRUCTIONS in out
    assert PATCH_INSTRUCTIONS_TOOLS_ACTIVE not in out


def test_system_prompt_tool_mode_swaps_preamble():
    soul = _soul()
    out = build_system_prompt(soul, tools_active=True)
    assert PATCH_INSTRUCTIONS_TOOLS_ACTIVE in out
    assert PATCH_INSTRUCTIONS not in out


def test_system_prompt_includes_context_when_present():
    soul = _soul(context="Extra lore context.")
    out = build_system_prompt(soul, tools_active=False)
    assert "Extra lore context." in out


def test_system_prompt_omits_empty_context():
    soul = _soul(context="")
    out = build_system_prompt(soul, tools_active=False)
    # The blank context slot should not produce adjacent "\n\n\n" sections.
    assert "\n\n\n" not in out


def test_system_prompt_includes_addendum_at_end():
    soul = _soul(addendum="Final rules appendix.")
    out = build_system_prompt(soul, tools_active=False)
    assert out.rstrip().endswith("Final rules appendix.")


def test_system_prompt_omits_empty_addendum():
    soul = _soul(addendum="")
    out = build_system_prompt(soul, tools_active=False)
    assert "\n\n\n" not in out


def test_system_prompt_section_order():
    soul = _soul(context="CTX", addendum="ADD")
    out = build_system_prompt(soul, tools_active=False)
    # mission → persona → context → instructions → addendum
    mission_i = out.index("Your mission is to test.")
    persona_i = out.index("You are a helpful test agent.")
    ctx_i = out.index("CTX")
    instr_i = out.index("Respond using ONLY")
    add_i = out.index("ADD")
    assert mission_i < persona_i < ctx_i < instr_i < add_i


# --- build_user_message ---


def test_user_message_minimum():
    out = build_user_message(
        memory_summary="",
        current_goal="",
        current_plan=[],
        plan_exhausted=False,
        idle_wakeup_count=0,
        window_lines=[],
    )
    # With no state, only the empty window join and the trailing prompt appear.
    assert out.endswith("What should you do next?")


def test_user_message_memory_summary_included():
    out = build_user_message(
        memory_summary="Previously visited the library.",
        current_goal="",
        current_plan=[],
        plan_exhausted=False,
        idle_wakeup_count=0,
        window_lines=[],
    )
    assert "[Earlier context: Previously visited the library.]" in out


def test_user_message_current_goal_included():
    out = build_user_message(
        memory_summary="",
        current_goal="build the library",
        current_plan=[],
        plan_exhausted=False,
        idle_wakeup_count=0,
        window_lines=[],
    )
    assert "Current goal: build the library" in out


def test_user_message_current_plan_joined_with_pipes():
    out = build_user_message(
        memory_summary="",
        current_goal="",
        current_plan=["look", "go north", "@dig east"],
        plan_exhausted=False,
        idle_wakeup_count=0,
        window_lines=[],
    )
    assert "Remaining plan: look | go north | @dig east" in out


def test_user_message_plan_exhausted_overrides_plan_line():
    out = build_user_message(
        memory_summary="",
        current_goal="",
        current_plan=[],
        plan_exhausted=True,
        idle_wakeup_count=0,
        window_lines=[],
    )
    assert "All planned rooms are built." in out
    assert "page your successor" in out
    assert "call done()" in out


def test_user_message_plan_exhausted_hidden_when_plan_present():
    """A live plan takes priority over the exhausted-marker fallback."""
    out = build_user_message(
        memory_summary="",
        current_goal="",
        current_plan=["one", "two"],
        plan_exhausted=True,
        idle_wakeup_count=0,
        window_lines=[],
    )
    assert "Remaining plan: one | two" in out
    assert "All planned rooms are built." not in out


def test_user_message_idle_wakeup_counter_included():
    out = build_user_message(
        memory_summary="",
        current_goal="",
        current_plan=[],
        plan_exhausted=False,
        idle_wakeup_count=3,
        window_lines=[],
    )
    assert "[Idle wakeups since last server output: 3]" in out


def test_user_message_idle_wakeup_hidden_when_zero():
    out = build_user_message(
        memory_summary="",
        current_goal="",
        current_plan=[],
        plan_exhausted=False,
        idle_wakeup_count=0,
        window_lines=[],
    )
    assert "Idle wakeups" not in out


def test_user_message_window_lines_joined():
    out = build_user_message(
        memory_summary="",
        current_goal="",
        current_plan=[],
        plan_exhausted=False,
        idle_wakeup_count=0,
        window_lines=["You see a room.", "There is a door here."],
    )
    assert "You see a room." in out
    assert "There is a door here." in out


def test_user_message_section_order():
    out = build_user_message(
        memory_summary="prior context",
        current_goal="the goal",
        current_plan=["step1", "step2"],
        plan_exhausted=False,
        idle_wakeup_count=2,
        window_lines=["server line"],
    )
    mem_i = out.index("[Earlier context")
    goal_i = out.index("Current goal")
    plan_i = out.index("Remaining plan")
    idle_i = out.index("Idle wakeups")
    window_i = out.index("server line")
    prompt_i = out.index("What should you do next?")
    assert mem_i < goal_i < plan_i < idle_i < window_i < prompt_i
