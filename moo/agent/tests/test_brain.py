"""
Tests for moo/agent/brain.py.

Tests rule matching, intent resolution, and compile_rules — no LLM calls, no
asyncio runtime needed for the pure logic paths. Does not require
DJANGO_SETTINGS_MODULE.
"""
# pylint: disable=protected-access

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock

import pytest

from moo.agent.brain import Brain, Status, looks_like_error, _SCRIPT_RE
from moo.agent.soul import Rule, Soul, VerbMapping, compile_rules
from moo.agent.tools import BUILDER_TOOLS, LLMResponse, ToolSpec, ToolParam


@dataclass
class _FakeAgentConfig:
    command_rate_per_second: float = 10.0
    memory_window_lines: int = 50
    idle_wakeup_seconds: float = 60.0
    max_tokens: int = 2048
    stall_timeout_seconds: int = 0


@dataclass
class _FakeLLMConfig:
    provider: str = "anthropic"
    model: str = "claude-opus-4-6"
    api_key_env: str = "ANTHROPIC_API_KEY"
    aws_region: str = "us-east-1"
    base_url: str = ""


@dataclass
class _FakeConfig:
    agent: Optional[_FakeAgentConfig] = None
    llm: Optional[_FakeLLMConfig] = None

    def __post_init__(self):
        if self.agent is None:
            self.agent = _FakeAgentConfig()
        if self.llm is None:
            self.llm = _FakeLLMConfig()


def _make_brain(soul=None, config_dir=None, on_status_change=None, tools=None):
    if soul is None:
        soul = Soul()
    config = _FakeConfig()
    sent = []
    thoughts = []
    brain = Brain(
        soul=soul,
        config=config,
        send_command=sent.append,
        on_thought=thoughts.append,
        config_dir=config_dir,
        on_status_change=on_status_change,
        tools=tools,
    )
    return brain, sent, thoughts


def _make_text_block(text: str):
    """Create a fake Anthropic TextBlock."""

    class _Block:
        def __init__(self, t):
            self.type = "text"
            self.text = t

    return _Block(text)


def _make_tool_use_block(name: str, input_dict: dict):
    """Create a fake Anthropic ToolUseBlock."""

    class _Block:
        def __init__(self, n, i):
            self.type = "tool_use"
            self.name = n
            self.input = i

    return _Block(name, input_dict)


def _fake_anthropic_client(text: str = "", tool_calls: list | None = None):
    """Return a mock Anthropic client whose messages.create returns text + optional tool calls."""
    blocks = [_make_text_block(text)]
    for name, args in tool_calls or []:
        blocks.append(_make_tool_use_block(name, args))

    async def _create(**kwargs):
        class _Resp:
            content = blocks

        return _Resp()

    client = MagicMock()
    client.messages.create = _create
    return client


def test_check_rules_match():
    soul = Soul(rules=[Rule(pattern="^You feel hungry", command="eat food")])
    brain, _, _ = _make_brain(soul)
    brain._compiled_rules = compile_rules(soul)
    result = brain._check_rules("You feel hungry in the Manor")
    assert result == "eat food"


def test_check_rules_no_match():
    soul = Soul(rules=[Rule(pattern="^You feel hungry", command="eat food")])
    brain, _, _ = _make_brain(soul)
    brain._compiled_rules = compile_rules(soul)
    result = brain._check_rules("The room is bright and cheerful")
    assert result is None


def test_check_rules_first_match_wins():
    soul = Soul(
        rules=[
            Rule(pattern="hungry", command="eat food"),
            Rule(pattern="hungry", command="drink water"),
        ]
    )
    brain, _, _ = _make_brain(soul)
    brain._compiled_rules = compile_rules(soul)
    result = brain._check_rules("You feel hungry")
    assert result == "eat food"


def test_resolve_intent_known():
    soul = Soul(verb_mappings=[VerbMapping(intent="look_around", template="look")])
    brain, _, _ = _make_brain(soul)
    result = brain._resolve_intent("look_around")
    assert result == "look"


def test_resolve_intent_case_insensitive():
    soul = Soul(verb_mappings=[VerbMapping(intent="Look_Around", template="look")])
    brain, _, _ = _make_brain(soul)
    result = brain._resolve_intent("look_around")
    assert result == "look"


def test_resolve_intent_unknown_passthrough():
    soul = Soul()
    brain, _, _ = _make_brain(soul)
    result = brain._resolve_intent("go north")
    assert result == "go north"


def test_compile_rules_empty():
    soul = Soul()
    compiled = compile_rules(soul)
    assert compiled == []


def test_compile_rules_returns_patterns():
    soul = Soul(
        rules=[
            Rule(pattern="^hungry", command="eat"),
            Rule(pattern="(?i)ring.*bell", command="say Hello"),
        ]
    )
    compiled = compile_rules(soul)
    assert len(compiled) == 2
    assert all(isinstance(p, re.Pattern) for p, _ in compiled)
    pattern0, _ = compiled[0]
    assert pattern0.search("hungry now")
    assert not pattern0.search("  hungry now")  # ^ anchor


def test_apply_patch_updates_rules(tmp_path):
    soul_content = "# Name\nTest\n# Mission\nM\n# Persona\nP\n"
    (tmp_path / "SOUL.md").write_text(soul_content)
    soul = Soul()
    brain, _, _ = _make_brain(soul, config_dir=tmp_path)
    brain._apply_patch("rule", "^You are thirsty -> drink water")
    assert any(r.pattern == "^You are thirsty" for r in brain._soul.rules)


def test_apply_patch_bad_directive_ignored(tmp_path):
    soul_content = "# Name\nTest\n# Mission\nM\n# Persona\nP\n"
    (tmp_path / "SOUL.md").write_text(soul_content)
    soul = Soul()
    brain, _, _ = _make_brain(soul, config_dir=tmp_path)
    # No arrow — should be silently ignored
    brain._apply_patch("rule", "no arrow here")
    assert brain._soul.rules == []


def test_apply_patch_no_config_dir_noop():
    soul = Soul()
    brain, _, _ = _make_brain(soul, config_dir=None)
    brain._apply_patch("rule", "trigger -> command")
    # Should not raise; soul remains empty
    assert brain._soul.rules == []


def test_apply_patch_note_written_to_file(tmp_path):
    (tmp_path / "SOUL.md").write_text("# Name\nTest\n# Mission\nM\n# Persona\nP\n")
    soul = Soul()
    brain, _, _ = _make_brain(soul, config_dir=tmp_path)
    brain._apply_patch("note", "obj.name is a model field — always call obj.save()")
    text = (tmp_path / "SOUL.patch.md").read_text()
    assert "obj.name is a model field" in text
    assert "## Lessons Learned" in text


def test_apply_patch_note_no_arrow_required(tmp_path):
    (tmp_path / "SOUL.md").write_text("# Name\nTest\n# Mission\nM\n# Persona\nP\n")
    soul = Soul()
    brain, _, _ = _make_brain(soul, config_dir=tmp_path)
    # Notes with no arrow should be stored, unlike rules which need "pattern -> command"
    brain._apply_patch("note", "plain note with no arrow")
    text = (tmp_path / "SOUL.patch.md").read_text()
    assert "plain note with no arrow" in text


def test_apply_patch_note_reloads_context(tmp_path):
    (tmp_path / "SOUL.md").write_text("# Name\nTest\n# Mission\nM\n# Persona\nP\n")
    soul = Soul()
    brain, _, _ = _make_brain(soul, config_dir=tmp_path)
    brain._apply_patch("note", "Always check exits before digging")
    assert "Always check exits before digging" in brain._soul.context


def test_llm_cycle_parses_soul_patch_note(tmp_path):
    import asyncio

    (tmp_path / "SOUL.md").write_text("# Name\nTest\n# Mission\nM\n# Persona\nP\n")
    soul = Soul()
    brain, _, _ = _make_brain(soul, config_dir=tmp_path)
    brain._client = _fake_anthropic_client(
        "SOUL_PATCH_NOTE: obj.name needs obj.save() to persist\nGOAL: continue\nCOMMAND: look"
    )

    asyncio.run(brain._llm_cycle())
    text = (tmp_path / "SOUL.patch.md").read_text()
    assert "obj.name needs obj.save()" in text


# --- Status / on_status_change tests ---


def test_status_enum_values():
    assert Status.READY.value == "ready"
    assert Status.SLEEPING.value == "sleeping"
    assert Status.THINKING.value == "thinking"


def test_set_status_calls_callback():
    events = []
    brain, _, _ = _make_brain(on_status_change=events.append)
    brain._set_status(Status.SLEEPING)
    assert events == [Status.SLEEPING]


def test_set_status_no_duplicate_callback():
    events = []
    brain, _, _ = _make_brain(on_status_change=events.append)
    brain._set_status(Status.READY)  # already INTERACT at start
    assert not events


def test_set_status_sequences():
    events = []
    brain, _, _ = _make_brain(on_status_change=events.append)
    brain._set_status(Status.THINKING)
    brain._set_status(Status.THINKING)  # duplicate — no extra event
    brain._set_status(Status.READY)
    assert events == [Status.THINKING, Status.READY]


def test_enqueue_output_resets_activity_time():
    import time

    brain, _, _ = _make_brain()
    old_time = brain._last_activity
    time.sleep(0.01)
    brain.enqueue_output("hello")
    assert brain._last_activity > old_time


# --- goal / plan / memory state ---


def test_initial_goal_and_plan_empty():
    brain, _, _ = _make_brain()
    assert brain._current_goal == ""
    assert brain._current_plan == []
    assert brain._memory_summary == ""


def test_build_user_message_bare_window():
    brain, _, _ = _make_brain()
    brain._window.append("You are in the Great Hall.")
    msg = brain._build_user_message()
    assert "You are in the Great Hall." in msg
    assert "What should you do next?" in msg


def test_build_user_message_includes_goal():
    brain, _, _ = _make_brain()
    brain._current_goal = "find the brass key"
    brain._window.append("You are in the Great Hall.")
    msg = brain._build_user_message()
    assert "Current goal: find the brass key" in msg


def test_build_user_message_includes_plan():
    brain, _, _ = _make_brain()
    brain._current_plan = ["go north", "look", "take key"]
    brain._window.append("You are in the Great Hall.")
    msg = brain._build_user_message()
    assert "Remaining plan: go north | look | take key" in msg


def test_build_user_message_includes_memory_summary():
    brain, _, _ = _make_brain()
    brain._memory_summary = "The agent explored three rooms and found a lantern."
    brain._window.append("You are in the Great Hall.")
    msg = brain._build_user_message()
    assert "Earlier context" in msg
    assert "lantern" in msg


def test_build_user_message_goal_plan_and_summary_ordering():
    brain, _, _ = _make_brain()
    brain._memory_summary = "Earlier summary."
    brain._current_goal = "find key"
    brain._current_plan = ["go north", "take key"]
    brain._window.append("Room output.")
    msg = brain._build_user_message()
    # Summary comes before goal, goal before plan, plan before window content
    assert msg.index("Earlier summary") < msg.index("Current goal")
    assert msg.index("Current goal") < msg.index("Remaining plan")
    assert msg.index("Remaining plan") < msg.index("Room output")


# --- looks_like_error ---


def testlooks_like_error_true():
    assert looks_like_error("Error: verb not found")
    assert looks_like_error("TypeError: expected str")
    assert looks_like_error("Traceback (most recent call last):")
    assert looks_like_error("  Error: leading whitespace")


def testlooks_like_error_false():
    assert not looks_like_error("Room created successfully.")
    assert not looks_like_error("Description set.")
    assert not looks_like_error("")


# --- _SCRIPT_RE ---


def test_script_re_matches_pipe_delimited():
    m = _SCRIPT_RE.match("SCRIPT: go north | @describe here as 'hall' | @create chair")
    assert m is not None
    steps = [s.strip() for s in m.group(1).split("|")]
    assert steps == ["go north", "@describe here as 'hall'", "@create chair"]


def test_script_re_no_match_on_command_line():
    assert _SCRIPT_RE.match("COMMAND: go north") is None


def test_script_re_no_match_on_plain_text():
    assert _SCRIPT_RE.match("You are in the Great Hall.") is None


# --- _script_queue initial state ---


def test_script_queue_starts_empty():
    brain, _, _ = _make_brain()
    assert brain._script_queue == []


# --- _handle_script_line ---


def test_handle_script_line_populates_queue():
    brain, _, _ = _make_brain()
    brain._handle_script_line("SCRIPT: go north | look | take key")
    assert brain._script_queue == ["go north", "look", "take key"]


def test_handle_script_line_strips_whitespace():
    brain, _, _ = _make_brain()
    brain._handle_script_line("SCRIPT:  go north  |  look  ")
    assert brain._script_queue == ["go north", "look"]


def test_handle_script_line_skips_empty_steps():
    brain, _, _ = _make_brain()
    brain._handle_script_line("SCRIPT: go north | | look")
    assert brain._script_queue == ["go north", "look"]


def test_handle_script_line_no_match_leaves_queue_empty():
    brain, _, _ = _make_brain()
    brain._handle_script_line("COMMAND: go north")
    assert brain._script_queue == []


def test_handle_script_line_emits_thought():
    brain, _, thoughts = _make_brain()
    brain._handle_script_line("SCRIPT: go north | look")
    assert any("Script" in t for t in thoughts)


# --- _drain_script ---


def test_drain_script_dispatches_next_command():
    brain, sent, _ = _make_brain()
    brain._script_queue = ["go north", "look", "take key"]
    result = brain._drain_script()
    assert result is True
    assert sent == ["go north"]
    assert brain._script_queue == ["look", "take key"]


def test_drain_script_noop_when_queue_empty():
    brain, sent, _ = _make_brain()
    result = brain._drain_script()
    assert result is False
    assert not sent


def test_drain_script_last_step_does_not_emit_complete_immediately():
    """[Script] Complete. is deferred to run() so it appears after the last response."""
    brain, sent, thoughts = _make_brain()
    brain._script_queue = ["look"]
    brain._drain_script()
    assert sent == ["look"]
    assert brain._script_queue == []
    assert not any("Complete" in t for t in thoughts)


def test_handle_script_line_sets_default_pending_done_msg():
    brain, _, _ = _make_brain()
    brain._handle_script_line("SCRIPT: go north | look")
    assert brain._pending_done_msg == "[Script] 0/2 remaining."


def test_drain_script_records_command_in_window():
    brain, _, _ = _make_brain()
    brain._script_queue = ["go north"]
    brain._drain_script()
    assert any("go north" in line for line in brain._window)


# --- Script kickoff from _llm_cycle ---


def test_handle_script_line_leaves_rest_in_queue():
    """After _handle_script_line, full list is in queue (no auto-pop)."""
    brain, _, _ = _make_brain()
    brain._handle_script_line("SCRIPT: go north | look | take key")
    assert brain._script_queue == ["go north", "look", "take key"]


def test_run_clears_script_queue_on_error():
    """run() clears the script queue when error output arrives, not _drain_script."""
    import asyncio

    brain, sent, thoughts = _make_brain()
    brain._script_queue = ["go north", "look"]

    async def _run_one_cycle():
        brain.enqueue_output("Error: no exit in that direction")
        # run() reads one item then waits; cancel after one iteration
        task = asyncio.ensure_future(brain.run())
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(_run_one_cycle())
    assert brain._script_queue == []
    assert not sent
    assert any("Error detected" in t for t in thoughts)


def test_llm_cycle_parses_done_directive():
    """DONE: line overrides the default pending_done_msg."""
    import asyncio

    brain, _, thoughts = _make_brain()
    brain._client = _fake_anthropic_client("GOAL: survey\nSCRIPT: look | go north\nDONE: Surveyed the area.")

    asyncio.run(brain._llm_cycle())
    # DONE: stored, not yet emitted (emitted at start of next _llm_cycle)
    assert brain._pending_done_msg == "Surveyed the area."
    assert not any("Surveyed the area" in t for t in thoughts)


def test_llm_cycle_emits_pending_done_msg_at_start():
    """Pending done message is emitted at the start of the next _llm_cycle."""
    import asyncio

    brain, _, thoughts = _make_brain()
    brain._pending_done_msg = "Script finished."
    brain._client = _fake_anthropic_client("GOAL: next\nCOMMAND: look")

    asyncio.run(brain._llm_cycle())
    assert any("Script finished." in t for t in thoughts)
    assert brain._pending_done_msg == ""


def test_llm_cycle_kicks_off_first_script_step():
    """
    When the LLM emits SCRIPT: with no COMMAND:, _llm_cycle should dispatch
    the first step immediately, leaving the rest in the queue for _drain_script.
    """
    import asyncio

    brain, sent, _ = _make_brain()
    brain._client = _fake_anthropic_client(
        'I\'ll survey the rooms.\nGOAL: map rooms\nSCRIPT: @move me to "Room A" | @show here | @move me to "Room B" | @show here'
    )

    asyncio.run(brain._llm_cycle())

    # First step dispatched immediately
    assert sent == ['@move me to "Room A"']
    # Remaining steps still in queue
    assert brain._script_queue == ["@show here", '@move me to "Room B"', "@show here"]


# --- BUILD_PLAN / _save_build_plan ---


def test_save_build_plan_creates_yaml_file(tmp_path):
    """_save_build_plan creates a datestamped .yaml file in builds/."""
    brain, _, thoughts = _make_brain(config_dir=tmp_path)
    brain._save_build_plan("phase: Test\\nrooms:\\n  - Room A")
    builds_dir = tmp_path / "builds"
    assert builds_dir.exists()
    files = list(builds_dir.glob("*.yaml"))
    assert len(files) == 1
    assert any("[Build Plan]" in t for t in thoughts)


def test_save_build_plan_expands_newlines(tmp_path):
    """\\n in the plan content is expanded to real newlines in the written file."""
    brain, _, _ = _make_brain(config_dir=tmp_path)
    brain._save_build_plan("phase: Test\\nrooms:\\n  - Room A")
    files = list((tmp_path / "builds").glob("*.yaml"))
    content = files[0].read_text()
    assert "phase: Test\n" in content
    assert "  - Room A" in content


def test_save_build_plan_no_config_dir_is_noop():
    """_save_build_plan silently does nothing when config_dir is None."""
    brain, _, _ = _make_brain(config_dir=None)
    brain._save_build_plan("phase: Test")  # must not raise


def test_llm_cycle_handles_build_plan_directive(tmp_path):
    """BUILD_PLAN: in LLM response creates a YAML file in builds/."""
    import asyncio

    (tmp_path / "SOUL.md").write_text("# Name\nTest\n# Mission\nM\n# Persona\nP\n")
    soul = Soul()
    brain, sent, _ = _make_brain(soul, config_dir=tmp_path)
    brain._client = _fake_anthropic_client(
        'BUILD_PLAN: phase: "Acid Wing"\\nrooms:\\n  - The Acid Bath\nGOAL: build phase\nCOMMAND: look'
    )

    asyncio.run(brain._llm_cycle())

    builds_dir = tmp_path / "builds"
    assert builds_dir.exists()
    files = list(builds_dir.glob("*.yaml"))
    assert len(files) == 1
    content = files[0].read_text()
    assert "Acid Wing" in content
    assert "The Acid Bath" in content
    assert sent == ["look"]


# --- Tool harness integration ---


def test_brain_stores_tools():
    dig = BUILDER_TOOLS[0]
    brain, _, _ = _make_brain(tools=[dig])
    assert brain._tools == [dig]


def test_brain_no_tools_default():
    brain, _, _ = _make_brain()
    assert brain._tools == []


def test_llm_cycle_tool_call_queues_commands():
    """A single tool_use block from the LLM is translated to MOO commands."""
    import asyncio

    brain, sent, _ = _make_brain(tools=BUILDER_TOOLS)
    brain._client = _fake_anthropic_client(
        "GOAL: build the library",
        tool_calls=[("dig", {"direction": "north", "room_name": "The Library"})],
    )

    asyncio.run(brain._llm_cycle())

    assert sent == ['@dig north to "The Library"']


def test_llm_cycle_multiple_tool_calls_batch_in_order():
    """Multiple tool_use blocks are batched into the script queue in order."""
    import asyncio

    brain, sent, _ = _make_brain(tools=BUILDER_TOOLS)
    brain._client = _fake_anthropic_client(
        "GOAL: build and enter",
        tool_calls=[
            ("dig", {"direction": "north", "room_name": "The Vault"}),
            ("go", {"direction": "north"}),
            ("describe", {"target": "here", "text": "A cold stone vault."}),
        ],
    )

    asyncio.run(brain._llm_cycle())

    # First command dispatched immediately; remainder in queue
    assert sent == ['@dig north to "The Vault"']
    assert brain._script_queue == ["go north", '@describe here as "A cold stone vault."']


def test_llm_cycle_done_tool_clears_goal():
    """The done tool clears the current goal and stores a pending message."""
    import asyncio

    brain, sent, _ = _make_brain(tools=BUILDER_TOOLS)
    brain._current_goal = "build the library"
    brain._client = _fake_anthropic_client(
        "",
        tool_calls=[("done", {"summary": "Library built with shelves and a reading table."})],
    )

    asyncio.run(brain._llm_cycle())

    assert brain._current_goal == ""
    assert "Library built" in brain._pending_done_msg
    assert not sent  # done tool emits no MOO command


def test_llm_cycle_unknown_tool_skips_with_thought():
    """An unknown tool name is logged as a thought and skipped."""
    import asyncio

    brain, sent, thoughts = _make_brain(tools=BUILDER_TOOLS)
    brain._client = _fake_anthropic_client(
        "GOAL: test",
        tool_calls=[("nonexistent_tool", {"foo": "bar"})],
    )

    asyncio.run(brain._llm_cycle())

    assert not sent
    assert any("Unknown tool" in t for t in thoughts)


def test_llm_cycle_tools_active_uses_tools_prompt():
    """When tools are configured, _PATCH_INSTRUCTIONS_TOOLS_ACTIVE is in the system prompt."""
    import asyncio
    from moo.agent.brain import _PATCH_INSTRUCTIONS_TOOLS_ACTIVE

    captured_kwargs = {}

    brain, _, _ = _make_brain(tools=BUILDER_TOOLS)

    async def _capture(**kwargs):
        captured_kwargs.update(kwargs)

        class _Resp:
            content = [_make_text_block("GOAL: done\nCOMMAND: look")]

        return _Resp()

    brain._client = MagicMock()
    brain._client.messages.create = _capture

    asyncio.run(brain._llm_cycle())

    system = captured_kwargs.get("system", "")
    assert _PATCH_INSTRUCTIONS_TOOLS_ACTIVE in system


def test_llm_cycle_no_tools_uses_standard_prompt():
    """When no tools are configured, _PATCH_INSTRUCTIONS (not tools variant) is used."""
    import asyncio
    from moo.agent.brain import _PATCH_INSTRUCTIONS, _PATCH_INSTRUCTIONS_TOOLS_ACTIVE

    captured_kwargs = {}

    brain, _, _ = _make_brain(tools=[])

    async def _capture(**kwargs):
        captured_kwargs.update(kwargs)

        class _Resp:
            content = [_make_text_block("GOAL: done\nCOMMAND: look")]

        return _Resp()

    brain._client = MagicMock()
    brain._client.messages.create = _capture

    asyncio.run(brain._llm_cycle())

    system = captured_kwargs.get("system", "")
    assert _PATCH_INSTRUCTIONS in system
    assert _PATCH_INSTRUCTIONS_TOOLS_ACTIVE not in system


# --- Room list deduplication ---


def test_token_page_strips_duplicate_rooms():
    """Rooms: clause is not appended twice when the message already contains one."""
    import asyncio

    brain, sent, _ = _make_brain(tools=BUILDER_TOOLS)
    brain._current_plan = ["#89"]
    brain._client = _fake_anthropic_client(
        tool_calls=[("page", {"target": "mason", "message": "Token: mason go. Rooms: #89"})]
    )
    asyncio.run(brain._llm_cycle())
    assert len(sent) == 1
    assert sent[0].count("Rooms:") == 1


# --- Fallback dispatch guard ---


def test_fallback_prose_not_dispatched():
    """Long internal-monologue lines must not be sent to the MOO server."""
    import asyncio

    brain, sent, _ = _make_brain()
    brain._client = _fake_anthropic_client("I am scanning the rolling window and awaiting the Token: Mason done. page.")
    asyncio.run(brain._llm_cycle())
    assert not sent


def test_fallback_short_command_dispatched():
    """A short (<=4 word) candidate is still dispatched."""
    import asyncio

    brain, sent, _ = _make_brain()
    brain._client = _fake_anthropic_client("look")
    asyncio.run(brain._llm_cycle())
    assert sent == ["look"]


def test_fallback_at_command_dispatched():
    """Commands starting with @ are always dispatched."""
    import asyncio

    brain, sent, _ = _make_brain()
    brain._client = _fake_anthropic_client("@rooms")
    asyncio.run(brain._llm_cycle())
    assert sent == ["@rooms"]


# --- Idle wakeup counter in user message ---


def test_build_user_message_no_wakeup_counter_at_zero():
    brain, _, _ = _make_brain()
    brain._idle_wakeup_count = 0
    brain._window.append("You are in the Great Hall.")
    msg = brain._build_user_message()
    assert "Idle wakeup" not in msg


def test_build_user_message_includes_wakeup_counter():
    brain, _, _ = _make_brain()
    brain._idle_wakeup_count = 5
    brain._window.append("You are in the Great Hall.")
    msg = brain._build_user_message()
    assert "[Idle wakeups since last server output: 5]" in msg


def test_build_user_message_wakeup_counter_before_window():
    """Counter must appear before the rolling window content."""
    brain, _, _ = _make_brain()
    brain._idle_wakeup_count = 3
    brain._window.append("Room output here.")
    msg = brain._build_user_message()
    assert msg.index("Idle wakeups") < msg.index("Room output here")
