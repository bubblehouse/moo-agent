"""
Tests for moo/agent/brain_prompt.py — pure string construction.

Both builders are pure functions with no Brain state. These tests pin the
exact shape of the output for each branch so we catch any drift when the
prompt preambles change.
"""

from moo.agent.brain.prompt import (
    RESPONSE_FORMAT,
    build_system_prompt,
    render_tools,
)
from moo.agent.soul import Soul
from moo.agent.tools import BUILDER_TOOLS_BY_NAME

# build_user_message is unchanged; import it separately so the test below
# still exercises it.
from moo.agent.brain.prompt import build_user_message  # noqa: E402


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


_TOOLS = [BUILDER_TOOLS_BY_NAME["dig"], BUILDER_TOOLS_BY_NAME["go"]]


# --- build_system_prompt ---


def test_system_prompt_has_mission_persona_response_format():
    out = build_system_prompt(_soul(), _TOOLS)
    assert "Your mission is to test." in out
    assert "You are a helpful test agent." in out
    assert RESPONSE_FORMAT in out


def test_system_prompt_renders_tool_reference():
    out = build_system_prompt(_soul(), _TOOLS)
    assert "dig — args: direction, room_name" in out
    assert "go — args: direction" in out


def test_render_tools_marks_optional_params():
    out = render_tools([BUILDER_TOOLS_BY_NAME["create_object"]])
    # parent is optional → rendered as "(optional)"
    assert "create_object — args: name, parent (optional)" in out


def test_render_tools_no_arg_tool():
    out = render_tools([BUILDER_TOOLS_BY_NAME["rooms"]])
    # a zero-param tool renders the bare name, never "rooms()"
    assert "- rooms — no args:" in out
    assert "rooms()" not in out


def test_system_prompt_includes_context_when_present():
    out = build_system_prompt(_soul(context="Extra lore context."), _TOOLS)
    assert "Extra lore context." in out


def test_system_prompt_omits_empty_context():
    out = build_system_prompt(_soul(context=""), _TOOLS)
    # The blank context slot should not produce adjacent "\n\n\n" sections.
    assert "\n\n\n" not in out


def test_system_prompt_includes_addendum_at_end():
    out = build_system_prompt(_soul(addendum="Final rules appendix."), _TOOLS)
    assert out.rstrip().endswith("Final rules appendix.")


def test_system_prompt_omits_empty_addendum():
    out = build_system_prompt(_soul(addendum=""), _TOOLS)
    assert "\n\n\n" not in out


def test_system_prompt_section_order():
    soul = _soul(context="CTX", addendum="ADD")
    out = build_system_prompt(soul, _TOOLS)
    # mission → persona → context → response format → tools → addendum
    mission_i = out.index("Your mission is to test.")
    persona_i = out.index("You are a helpful test agent.")
    ctx_i = out.index("CTX")
    fmt_i = out.index(RESPONSE_FORMAT)
    tools_i = out.index("Available tools")
    add_i = out.index("ADD")
    assert mission_i < persona_i < ctx_i < fmt_i < tools_i < add_i


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
