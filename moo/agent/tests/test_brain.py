"""
Tests for moo/agent/brain.py.

Tests rule matching, intent resolution, compile_rules, and the structured
AgentResponse cycle. Does not require DJANGO_SETTINGS_MODULE.
"""
# pylint: disable=protected-access

import re
from dataclasses import dataclass, field
from typing import Optional
from unittest.mock import MagicMock

from moo.agent.brain import Brain, Status, looks_like_error
from moo.agent.brain.plans import extract_room_names_from_yaml as _extract_room_names_from_yaml
from moo.agent.response_model import Action, AgentResponse
from moo.agent.soul import Rule, Soul, VerbMapping, compile_rules
from moo.agent.tools import BUILDER_TOOLS, BUILDER_TOOLS_BY_NAME


@dataclass
class _FakeAgentConfig:
    command_rate_per_second: float = 10.0
    memory_window_lines: int = 50
    idle_wakeup_seconds: float = 60.0
    max_tokens: int = 2048
    stall_timeout_seconds: int = 0
    timer_only: bool = False
    clear_window_on_wakeup: bool = True
    temperature: float | None = None
    top_p: float | None = None
    top_k: int | None = None
    instructor_retries: int = 2
    token_chain: list = field(default_factory=list)


@dataclass
class _FakeLLMConfig:
    provider: str = "anthropic"
    model: str = "claude-opus-4-6"
    api_key_env: str = "ANTHROPIC_API_KEY"
    aws_region: str = "us-east-1"
    base_url: str = ""


@dataclass
class _FakeSSHConfig:
    user: str = ""
    host: str = "localhost"
    port: int = 8022


@dataclass
class _FakeConfig:
    agent: Optional[_FakeAgentConfig] = None
    llm: Optional[_FakeLLMConfig] = None
    ssh: Optional[_FakeSSHConfig] = None

    def __post_init__(self):
        if self.agent is None:
            self.agent = _FakeAgentConfig()
        if self.llm is None:
            self.llm = _FakeLLMConfig()
        if self.ssh is None:
            self.ssh = _FakeSSHConfig()


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


def _agent_response(goal="", *, actions=None, done=None, soul_patches=None, build_plan=None, plan=None, reasoning=""):
    """Build a validated AgentResponse for use as a fake LLM reply."""
    return AgentResponse(
        goal=goal,
        reasoning=reasoning,
        actions=actions or [],
        plan=plan,
        done=done,
        soul_patches=soul_patches or [],
        build_plan=build_plan,
    )


def _fake_client(response: AgentResponse, captured: dict | None = None):
    """Mock client whose messages.create returns a validated AgentResponse."""

    async def _create(**kwargs):
        if captured is not None:
            captured.update(kwargs)
        return response

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


def test_llm_cycle_applies_soul_patch_note(tmp_path):
    """A soul_patches entry in the AgentResponse is appended to SOUL.patch.md."""
    import asyncio

    (tmp_path / "SOUL.md").write_text("# Name\nTest\n# Mission\nM\n# Persona\nP\n")
    soul = Soul()
    brain, _, _ = _make_brain(soul, config_dir=tmp_path)
    brain._client = _fake_client(
        _agent_response(
            goal="continue",
            soul_patches=[{"kind": "note", "content": "obj.name needs obj.save() to persist"}],
            actions=[{"tool": "raw", "args": {"command": "look"}}],
        )
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
    assert brain._state.current_goal == ""
    assert not brain._state.current_plan
    assert brain._state.memory_summary == ""


def test_build_user_message_bare_window():
    brain, _, _ = _make_brain()
    brain._window.append("You are in the Great Hall.")
    msg = brain._build_user_message()
    assert "You are in the Great Hall." in msg
    assert "What should you do next?" in msg


def test_build_user_message_includes_goal():
    brain, _, _ = _make_brain()
    brain._state.current_goal = "find the brass key"
    brain._window.append("You are in the Great Hall.")
    msg = brain._build_user_message()
    assert "Current goal: find the brass key" in msg


def test_build_user_message_includes_plan():
    brain, _, _ = _make_brain()
    brain._state.current_plan = ["go north", "look", "take key"]
    brain._window.append("You are in the Great Hall.")
    msg = brain._build_user_message()
    assert "Remaining plan: go north | look | take key" in msg


def test_build_user_message_includes_memory_summary():
    brain, _, _ = _make_brain()
    brain._state.memory_summary = "The agent explored three rooms and found a lantern."
    brain._window.append("You are in the Great Hall.")
    msg = brain._build_user_message()
    assert "Earlier context" in msg
    assert "lantern" in msg


def test_build_user_message_goal_plan_and_summary_ordering():
    brain, _, _ = _make_brain()
    brain._state.memory_summary = "Earlier summary."
    brain._state.current_goal = "find key"
    brain._state.current_plan = ["go north", "take key"]
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


# --- _script_queue initial state ---


def test_script_queue_starts_empty():
    brain, _, _ = _make_brain()
    assert not brain._script_queue


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
    assert not brain._script_queue
    assert not any("Complete" in t for t in thoughts)


def test_drain_script_records_command_in_window():
    brain, _, _ = _make_brain()
    brain._script_queue = ["go north"]
    brain._drain_script()
    assert any("go north" in line for line in brain._window)


# --- Script queue from _llm_cycle ---


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
    assert not brain._script_queue
    assert not sent
    assert any("Error detected" in t for t in thoughts)


def test_session_done_blocks_output_wakeup():
    """After done() is called, enqueue_output() must not trigger a new LLM cycle."""
    import asyncio

    brain, sent, thoughts = _make_brain()
    brain._state.session_done = True
    brain._state.current_goal = ""

    async def _run_one_cycle():
        brain.enqueue_output("Flicker says: Is it Tuesday?")
        task = asyncio.ensure_future(brain.run())
        await asyncio.sleep(0.35)  # longer than the 0.3 s burst-settle delay
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(_run_one_cycle())
    # No LLM call should have been made
    assert not sent
    assert not any("LLM" in t or "cycle" in t.lower() for t in thoughts)


def test_llm_cycle_done_field_clears_goal():
    """The done field clears the goal and ends the session once foreman is paged."""
    import asyncio

    brain, _, _ = _make_brain(tools=BUILDER_TOOLS)
    brain._state.current_goal = "survey"
    brain._state.foreman_paged = True
    brain._client = _fake_client(_agent_response(goal="survey", done="Surveyed the area."))

    asyncio.run(brain._llm_cycle())
    assert brain._state.pending_done_msg == "Surveyed the area."
    assert brain._state.session_done is True
    assert brain._state.current_goal == ""


def test_llm_cycle_emits_pending_done_msg_at_start():
    """Pending done message is emitted at the start of the next _llm_cycle."""
    import asyncio

    brain, _, thoughts = _make_brain(tools=BUILDER_TOOLS)
    brain._state.pending_done_msg = "Script finished."
    brain._client = _fake_client(_agent_response(goal="next", actions=[{"tool": "raw", "args": {"command": "look"}}]))

    asyncio.run(brain._llm_cycle())
    assert any("Script finished." in t for t in thoughts)
    assert brain._state.pending_done_msg == ""


def test_llm_cycle_kicks_off_first_action():
    """
    When the LLM emits several actions, _llm_cycle dispatches the first
    immediately, leaving the rest in the queue for _drain_script.
    """
    import asyncio

    brain, sent, _ = _make_brain(tools=BUILDER_TOOLS)
    brain._client = _fake_client(
        _agent_response(
            goal="map rooms",
            actions=[
                {"tool": "raw", "args": {"command": '@move me to "Room A"'}},
                {"tool": "raw", "args": {"command": "@show here"}},
                {"tool": "raw", "args": {"command": '@move me to "Room B"'}},
            ],
        )
    )

    asyncio.run(brain._llm_cycle())

    assert sent == ['@move me to "Room A"']
    assert brain._script_queue == ["@show here", '@move me to "Room B"']


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


def test_llm_cycle_handles_build_plan_field(tmp_path):
    """A build_plan field in the AgentResponse creates a YAML file in builds/."""
    import asyncio

    (tmp_path / "SOUL.md").write_text("# Name\nTest\n# Mission\nM\n# Persona\nP\n")
    soul = Soul()
    brain, sent, _ = _make_brain(soul, config_dir=tmp_path)
    brain._client = _fake_client(
        _agent_response(
            goal="build phase",
            build_plan='phase: "Acid Wing"\nrooms:\n  - The Acid Bath',
            actions=[{"tool": "raw", "args": {"command": "look"}}],
        )
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


def test_brain_stores_tools_plus_system_tools():
    dig = BUILDER_TOOLS_BY_NAME["dig"]
    brain, _, _ = _make_brain(tools=[dig])
    names = {t.name for t in brain._tools}
    assert "dig" in names
    # raw + respond are always injected
    assert "raw" in names
    assert "respond" in names


def test_brain_no_tools_default_has_system_tools():
    brain, _, _ = _make_brain()
    names = {t.name for t in brain._tools}
    assert names == {"raw", "respond"}


def test_llm_cycle_action_queues_commands():
    """A single action from the LLM is translated to MOO commands."""
    import asyncio

    brain, sent, _ = _make_brain(tools=BUILDER_TOOLS)
    brain._client = _fake_client(
        _agent_response(
            goal="build the library",
            actions=[{"tool": "dig", "args": {"direction": "north", "room_name": "The Library"}}],
        )
    )

    asyncio.run(brain._llm_cycle())
    assert sent == ['@dig north to "The Library"']


def test_llm_cycle_multiple_actions_batch_in_order():
    """Multiple actions are batched into the script queue in order."""
    import asyncio

    brain, sent, _ = _make_brain(tools=BUILDER_TOOLS)
    brain._client = _fake_client(
        _agent_response(
            goal="build and enter",
            actions=[
                {"tool": "dig", "args": {"direction": "north", "room_name": "The Vault"}},
                {"tool": "go", "args": {"direction": "north"}},
                {"tool": "describe", "args": {"target": "here", "text": "A cold stone vault."}},
            ],
        )
    )

    asyncio.run(brain._llm_cycle())

    assert sent == ['@dig north to "The Vault"']
    assert brain._script_queue == ["go north", '@describe here as "A cold stone vault."']


def test_llm_cycle_done_action_clears_goal():
    """The done action clears the current goal when foreman has been paged."""
    import asyncio

    brain, sent, _ = _make_brain(tools=BUILDER_TOOLS)
    brain._state.current_goal = "build the library"
    brain._state.foreman_paged = True  # simulate prior page to foreman
    brain._client = _fake_client(
        _agent_response(
            goal="build the library",
            actions=[{"tool": "done", "args": {"summary": "Library built with shelves."}}],
        )
    )

    asyncio.run(brain._llm_cycle())

    assert brain._state.current_goal == ""
    assert "Library built" in brain._state.pending_done_msg
    assert not sent  # done emits no MOO command


def test_llm_cycle_done_action_blocked_without_foreman_page():
    """done is blocked and emits a thought when foreman has not been paged."""
    import asyncio

    brain, sent, thoughts = _make_brain(tools=BUILDER_TOOLS)
    brain._state.current_goal = "build the library"
    brain._state.foreman_paged = False
    brain._client = _fake_client(
        _agent_response(
            goal="build the library",
            actions=[{"tool": "done", "args": {"summary": "Library built."}}],
        )
    )

    asyncio.run(brain._llm_cycle())

    # goal is overwritten with the redirect instruction to page foreman first
    assert "page" in brain._state.current_goal and "foreman" in brain._state.current_goal
    assert not brain._state.session_done  # session not ended
    assert any("Blocked" in t for t in thoughts)
    assert not sent


def test_llm_cycle_plan_field_sets_current_plan():
    """The plan field records a room-traversal plan into Brain state."""
    import asyncio

    brain, _, _ = _make_brain(tools=BUILDER_TOOLS)
    brain._client = _fake_client(
        _agent_response(
            goal="traverse",
            plan=["#9", "#22", "#37"],
            actions=[{"tool": "raw", "args": {"command": "look"}}],
        )
    )

    asyncio.run(brain._llm_cycle())
    assert brain._state.current_plan == ["#9", "#22", "#37"]


def test_llm_cycle_null_plan_leaves_current_plan_untouched():
    """A response with no plan field leaves an existing plan in place."""
    import asyncio

    brain, _, _ = _make_brain(tools=BUILDER_TOOLS)
    brain._state.current_plan = ["#1", "#2"]
    brain._client = _fake_client(_agent_response(goal="work", actions=[{"tool": "raw", "args": {"command": "look"}}]))

    asyncio.run(brain._llm_cycle())
    assert brain._state.current_plan == ["#1", "#2"]


def test_respond_action_emits_thought_no_command():
    """A respond action routes its message to the thought channel, sends nothing."""
    import asyncio

    brain, sent, thoughts = _make_brain(tools=BUILDER_TOOLS)
    brain._client = _fake_client(
        _agent_response(goal="wait", actions=[{"tool": "respond", "args": {"message": "Idle until paged."}}])
    )

    asyncio.run(brain._llm_cycle())

    assert not sent
    assert any("Idle until paged." in t for t in thoughts)


def test_teleport_guard_skips_action_to_current_room():
    """A teleport action to the room we're already in is dropped before the queue."""
    import asyncio

    brain, sent, thoughts = _make_brain(tools=BUILDER_TOOLS)
    brain._state.current_room_id = "#52"
    brain._state.current_room_name = "Servants Stair"
    brain._client = _fake_client(
        _agent_response(goal="move", actions=[{"tool": "teleport", "args": {"destination": "#52"}}])
    )

    asyncio.run(brain._llm_cycle())

    assert not sent
    assert not brain._script_queue
    assert any("Skipping teleport(#52)" in t for t in thoughts)


def test_teleport_guard_allows_teleport_to_different_room():
    """A teleport action to a different room is translated and dispatched normally."""
    import asyncio

    brain, sent, _ = _make_brain(tools=BUILDER_TOOLS)
    brain._state.current_room_id = "#52"
    brain._state.current_room_name = "Servants Stair"
    brain._client = _fake_client(
        _agent_response(goal="move", actions=[{"tool": "teleport", "args": {"destination": "#99"}}])
    )

    asyncio.run(brain._llm_cycle())

    assert sent == ["teleport #99"]


def test_llm_cycle_tool_not_enabled_for_agent_skipped():
    """A valid tool that this agent has not enabled is skipped with a thought."""
    import asyncio

    # Agent only has `dig` enabled (plus the always-on raw/respond).
    brain, sent, thoughts = _make_brain(tools=[BUILDER_TOOLS_BY_NAME["dig"]])
    brain._client = _fake_client(_agent_response(goal="test", actions=[{"tool": "go", "args": {"direction": "north"}}]))

    asyncio.run(brain._llm_cycle())

    assert not sent
    assert any("Unknown tool" in t for t in thoughts)


def test_system_prompt_includes_response_format():
    """The structured-response format block is part of the system prompt."""
    import asyncio
    from moo.agent.brain.prompt import RESPONSE_FORMAT

    captured: dict = {}
    brain, _, _ = _make_brain(tools=BUILDER_TOOLS)
    brain._client = _fake_client(
        _agent_response(goal="done", actions=[{"tool": "raw", "args": {"command": "look"}}]),
        captured=captured,
    )

    asyncio.run(brain._llm_cycle())

    system_text = "".join(b.get("text", "") for b in captured.get("system", []))
    assert RESPONSE_FORMAT in system_text


# --- Token page ---


def test_token_page_dispatches_page_command():
    """A page action with a Token: message is translated and dispatched."""
    import asyncio

    brain, sent, _ = _make_brain(tools=BUILDER_TOOLS)
    brain._state.current_plan = ["#89"]
    brain._client = _fake_client(
        _agent_response(
            goal="hand off",
            actions=[{"tool": "page", "args": {"target": "mason", "message": "Token: mason go. Rooms: #89"}}],
        )
    )
    asyncio.run(brain._llm_cycle())
    assert len(sent) == 1
    assert sent[0].count("Rooms:") == 1


def test_token_page_starts_stall_timer():
    """A Token: page to a non-foreman target starts the stall timer."""
    import asyncio

    brain, _, _ = _make_brain(tools=BUILDER_TOOLS)
    brain._client = _fake_client(
        _agent_response(
            goal="hand off",
            actions=[{"tool": "page", "args": {"target": "tinker", "message": "Token: tinker go."}}],
        )
    )
    asyncio.run(brain._llm_cycle())
    assert brain._state.token_dispatched_to == "tinker"
    assert brain._state.token_dispatched_at is not None


# --- Reasoning is never dispatched ---


def test_reasoning_only_not_dispatched():
    """A response with reasoning but no actions sends nothing to the server."""
    import asyncio

    brain, sent, _ = _make_brain(tools=BUILDER_TOOLS)
    brain._client = _fake_client(
        _agent_response(goal="", reasoning="I am scanning the rolling window and awaiting the token.")
    )
    asyncio.run(brain._llm_cycle())
    assert not sent


def test_raw_action_dispatched():
    """A raw action is sent verbatim."""
    import asyncio

    brain, sent, _ = _make_brain(tools=BUILDER_TOOLS)
    brain._client = _fake_client(_agent_response(goal="look", actions=[{"tool": "raw", "args": {"command": "look"}}]))
    asyncio.run(brain._llm_cycle())
    assert sent == ["look"]


def test_raw_action_at_command_dispatched():
    """A raw action carrying an @-command is dispatched."""
    import asyncio

    brain, sent, _ = _make_brain(tools=BUILDER_TOOLS)
    brain._client = _fake_client(_agent_response(goal="list", actions=[{"tool": "raw", "args": {"command": "@rooms"}}]))
    asyncio.run(brain._llm_cycle())
    assert sent == ["@rooms"]


# --- Idle wakeup counter in user message ---


def test_build_user_message_no_wakeup_counter_at_zero():
    brain, _, _ = _make_brain()
    brain._state.idle_wakeup_count = 0
    brain._window.append("You are in the Great Hall.")
    msg = brain._build_user_message()
    assert "Idle wakeup" not in msg


def test_build_user_message_includes_wakeup_counter():
    brain, _, _ = _make_brain()
    brain._state.idle_wakeup_count = 5
    brain._window.append("You are in the Great Hall.")
    msg = brain._build_user_message()
    assert "[Idle wakeups since last server output: 5]" in msg


# --- extract_room_names_from_yaml ---


def test_extract_room_names_from_yaml_unquoted():
    yaml = "rooms:\n  - name: The Library\n  - name: The Vault\n"
    assert _extract_room_names_from_yaml(yaml) == ["The Library", "The Vault"]


def test_extract_room_names_from_yaml_quoted():
    yaml = "rooms:\n  - name: \"The Acid Bath\"\n  - name: 'The Boneyard'\n"
    assert _extract_room_names_from_yaml(yaml) == ["The Acid Bath", "The Boneyard"]


def test_extract_room_names_from_yaml_empty():
    assert _extract_room_names_from_yaml("phase: Build\n") == []


def test_extract_room_names_excludes_nested():
    """4-space-indented names (nested objects) must not be included."""
    yaml = "rooms:\n  - name: The Library\n    objects:\n      - name: A Shelf\n"
    assert _extract_room_names_from_yaml(yaml) == ["The Library"]


# --- Save plan error handling ---


def test_save_build_plan_oserror_does_not_raise(tmp_path):
    """OSError during write is caught and logged as a thought; no crash."""
    brain, _, thoughts = _make_brain(config_dir=tmp_path)
    # Make builds/ a file so mkdir fails
    (tmp_path / "builds").write_text("not a dir")
    brain._save_build_plan("phase: Test\\nrooms:\\n  - name: The Lab")
    assert any("Error saving" in t for t in thoughts)


def test_save_traversal_plan_oserror_does_not_raise(tmp_path):
    """OSError during traversal plan write is caught and logged as a thought."""
    brain, _, thoughts = _make_brain(config_dir=tmp_path)
    brain._state.current_plan = ["The Library", "The Vault"]
    # Make builds/ a file so mkdir fails
    (tmp_path / "builds").write_text("not a dir")
    brain._save_traversal_plan()
    assert any("Error saving" in t for t in thoughts)


def test_build_user_message_wakeup_counter_before_window():
    """Counter must appear before the rolling window content."""
    brain, _, _ = _make_brain()
    brain._state.idle_wakeup_count = 3
    brain._window.append("Room output here.")
    msg = brain._build_user_message()
    assert msg.index("Idle wakeups") < msg.index("Room output here")


# --- Cycle stats marker ---


def test_llm_cycle_emits_cycle_marker():
    """Every LLM cycle emits a single [Cycle] thought with duration and counts."""
    import asyncio

    brain, _, thoughts = _make_brain(tools=BUILDER_TOOLS)
    brain._client = _fake_client(
        _agent_response(
            goal="build the library",
            actions=[{"tool": "dig", "args": {"direction": "north", "room_name": "The Library"}}],
        )
    )

    asyncio.run(brain._llm_cycle())

    cycle_lines = [t for t in thoughts if t.startswith("[Cycle]")]
    assert len(cycle_lines) == 1
    line = cycle_lines[0]
    assert "duration=" in line
    assert "tool_calls=1" in line
    assert "commands=1" in line


def test_llm_cycle_marker_counts_batched_commands():
    """Multiple actions increment tool_calls and commands reflects queue size."""
    import asyncio

    brain, _, thoughts = _make_brain(tools=BUILDER_TOOLS)
    brain._client = _fake_client(
        _agent_response(
            goal="survey",
            actions=[
                {"tool": "raw", "args": {"command": "look"}},
                {"tool": "raw", "args": {"command": "go north"}},
                {"tool": "raw", "args": {"command": "inventory"}},
            ],
        )
    )

    asyncio.run(brain._llm_cycle())

    cycle_lines = [t for t in thoughts if t.startswith("[Cycle]")]
    assert len(cycle_lines) == 1
    line = cycle_lines[0]
    assert "tool_calls=3" in line
    assert "commands=3" in line


def test_llm_cycle_marker_resets_between_cycles():
    """Counters must reset between successive LLM cycles on the same brain."""
    import asyncio

    brain, _, thoughts = _make_brain(tools=BUILDER_TOOLS)
    brain._client = _fake_client(
        _agent_response(
            goal="first",
            actions=[{"tool": "dig", "args": {"direction": "north", "room_name": "Room A"}}],
        )
    )
    asyncio.run(brain._llm_cycle())
    # Drain the queue so the second cycle starts clean.
    brain._script_queue = []

    brain._client = _fake_client(
        _agent_response(
            goal="second",
            actions=[
                {"tool": "dig", "args": {"direction": "south", "room_name": "Room B"}},
                {"tool": "go", "args": {"direction": "south"}},
            ],
        )
    )
    asyncio.run(brain._llm_cycle())

    cycle_lines = [t for t in thoughts if t.startswith("[Cycle]")]
    assert len(cycle_lines) == 2
    assert "tool_calls=1" in cycle_lines[0]
    assert "commands=1" in cycle_lines[0]
    assert "tool_calls=2" in cycle_lines[1]
    assert "commands=2" in cycle_lines[1]


def test_llm_cycle_marker_emitted_on_llm_error():
    """Even when the LLM errors out, a [Cycle] marker records the attempt."""
    import asyncio

    brain, _, thoughts = _make_brain()

    async def _boom(**kwargs):
        raise RuntimeError("llm unreachable")

    brain._client = MagicMock()
    brain._client.messages.create = _boom

    asyncio.run(brain._llm_cycle())

    cycle_lines = [t for t in thoughts if t.startswith("[Cycle]")]
    assert len(cycle_lines) == 1
    line = cycle_lines[0]
    assert "tool_calls=0" in line
    assert "commands=0" in line


def test_run_llm_with_retry_maps_instructor_failure_to_none():
    """An exhausted Instructor retry budget surfaces as None (→ recovery path)."""
    import asyncio
    from instructor.core import InstructorRetryException

    brain, _, thoughts = _make_brain()

    async def _retry_exhausted(**kwargs):
        raise InstructorRetryException("validation failed", n_attempts=3, total_usage=0)

    brain._client = MagicMock()
    brain._client.messages.create = _retry_exhausted

    result = asyncio.run(brain._run_llm_with_retry("system", "user"))
    assert result is None
    assert any("structured-output validation failed" in t for t in thoughts)


def _fake_subprocess_exec(stdout_bytes: bytes, returncode: int = 0):
    """Return a coroutine that mimics asyncio.create_subprocess_exec."""

    class _FakeProc:
        def __init__(self):
            self.returncode = returncode

        async def communicate(self):
            return stdout_bytes, b""

    async def _exec(*args, **kwargs):
        return _FakeProc()

    return _exec


def test_stall_check_skips_repage_when_target_is_actively_cycling(monkeypatch):
    """age=120, p95=150 → adaptive=max(60, 450)=450 → still cycling."""
    import asyncio

    monkeypatch.setenv("MOO_TOKEN_CHAIN_GROUP", "tradesmen")
    monkeypatch.setenv("MOO_AGENTMUX_PATH", "/fake/agentmux")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_subprocess_exec(b"120 150.0\n", 0))

    brain, _, thoughts = _make_brain()
    result = asyncio.run(brain._target_is_actively_cycling("tinker", 60))

    assert result is True
    skip_lines = [t for t in thoughts if "still cycling" in t]
    assert len(skip_lines) == 1
    assert "tinker" in skip_lines[0]
    assert "elapsed=120s" in skip_lines[0]
    assert "3×p95=450s" in skip_lines[0]


def test_stall_check_repages_when_target_exceeds_adaptive_threshold(monkeypatch):
    """age=500, p95=100 → adaptive=max(60, 300)=300; 500 >= 300 → not cycling."""
    import asyncio

    monkeypatch.setenv("MOO_TOKEN_CHAIN_GROUP", "tradesmen")
    monkeypatch.setenv("MOO_AGENTMUX_PATH", "/fake/agentmux")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_subprocess_exec(b"500 100.0\n", 0))

    brain, _, thoughts = _make_brain()
    result = asyncio.run(brain._target_is_actively_cycling("tinker", 60))

    assert result is False
    assert not [t for t in thoughts if "still cycling" in t]


def test_stall_check_falls_through_when_env_vars_missing(monkeypatch):
    """Without env vars, helper returns False immediately without shelling out."""
    import asyncio

    monkeypatch.delenv("MOO_TOKEN_CHAIN_GROUP", raising=False)
    monkeypatch.delenv("MOO_AGENTMUX_PATH", raising=False)
    called = {"count": 0}

    async def _should_not_be_called(*args, **kwargs):
        called["count"] += 1
        raise AssertionError("subprocess should not be invoked")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _should_not_be_called)

    brain, _, thoughts = _make_brain()
    result = asyncio.run(brain._target_is_actively_cycling("tinker", 60))

    assert result is False
    assert called["count"] == 0
    assert not [t for t in thoughts if "still cycling" in t]


def test_stall_check_falls_through_on_subprocess_failure(monkeypatch):
    """Non-zero subprocess exit → helper returns False, no skip thought."""
    import asyncio

    monkeypatch.setenv("MOO_TOKEN_CHAIN_GROUP", "tradesmen")
    monkeypatch.setenv("MOO_AGENTMUX_PATH", "/fake/agentmux")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_subprocess_exec(b"", 2))

    brain, _, thoughts = _make_brain()
    result = asyncio.run(brain._target_is_actively_cycling("tinker", 60))

    assert result is False
    assert not [t for t in thoughts if "still cycling" in t]


def test_stall_check_falls_through_on_sentinel_values(monkeypatch):
    """`-1 -1` sentinel (no cycle data yet) → helper returns False."""
    import asyncio

    monkeypatch.setenv("MOO_TOKEN_CHAIN_GROUP", "tradesmen")
    monkeypatch.setenv("MOO_AGENTMUX_PATH", "/fake/agentmux")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_subprocess_exec(b"-1 -1.0\n", 0))

    brain, _, thoughts = _make_brain()
    result = asyncio.run(brain._target_is_actively_cycling("tinker", 60))

    assert result is False
    assert not [t for t in thoughts if "still cycling" in t]


def test_stall_check_honors_minimum_of_configured_timeout(monkeypatch):
    """3×p95=30s but stall_s=300s → adaptive=300; age=200<300 → still cycling."""
    import asyncio

    monkeypatch.setenv("MOO_TOKEN_CHAIN_GROUP", "tradesmen")
    monkeypatch.setenv("MOO_AGENTMUX_PATH", "/fake/agentmux")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_subprocess_exec(b"200 10.0\n", 0))

    brain, _, thoughts = _make_brain()
    result = asyncio.run(brain._target_is_actively_cycling("tinker", 300))

    assert result is True
    skip_lines = [t for t in thoughts if "still cycling" in t]
    assert len(skip_lines) == 1
    assert "elapsed=200s" in skip_lines[0]


def test_update_current_room_from_burrow_output():
    brain, _, _ = _make_brain()
    brain._state.current_room_name = "Binding Annex"
    brain._state.current_room_id = "#1146"
    brain._update_current_room_from(
        "Dug south to Vellum Store (#1189).\n"
        "Tunnelled north back to Binding Annex (#1146).\n"
        "You are now in Vellum Store (#1189)."
    )
    assert brain._state.current_room_name == "Vellum Store"
    assert brain._state.current_room_id == "#1189"


def test_update_current_room_from_move_output_still_works():
    brain, _, _ = _make_brain()
    brain._update_current_room_from("You move to Chart Vault (#1143).")
    assert brain._state.current_room_name == "Chart Vault"
    assert brain._state.current_room_id == "#1143"


def test_check_verb_test_mistake_injects_hint():
    brain, _, thoughts = _make_brain()
    brain._recent_cmds.append("look peer #1152")
    brain._check_verb_test_mistake("There is no 'peer #1152' here.")
    operator_lines = [line for line in brain._window if line.startswith("[Operator]:")]
    assert len(operator_lines) == 1
    assert "'peer #1152' directly" in operator_lines[0]
    assert "no 'look' prefix" in operator_lines[0]
    assert any("Verb-test mistake detected" in t for t in thoughts)


def test_check_verb_test_mistake_ignores_unrelated_errors():
    brain, _, thoughts = _make_brain()
    brain._recent_cmds.append("look brass lamp")
    brain._check_verb_test_mistake("There is no 'brass lamp' here.")
    operator_lines = [line for line in brain._window if line.startswith("[Operator]:")]
    assert operator_lines == []
    assert not any("Verb-test mistake" in t for t in thoughts)


def test_check_verb_test_mistake_ignores_when_last_cmd_isnt_look():
    brain, _, _ = _make_brain()
    brain._recent_cmds.append("peer #1152")
    brain._check_verb_test_mistake("There is no 'peer #1152' here.")
    operator_lines = [line for line in brain._window if line.startswith("[Operator]:")]
    assert operator_lines == []


def test_dispatch_actions_handles_translator_value_error():
    brain, _, thoughts = _make_brain(tools=BUILDER_TOOLS)
    brain._dispatch_actions([Action(tool="look", args={"target": "peer #1152"})])
    error_lines = [t for t in thoughts if "not how you test a verb" in t]
    assert len(error_lines) == 1
    operator_lines = [line for line in brain._window if line.startswith("[Operator]:")]
    assert len(operator_lines) == 1
    assert "not how you test a verb" in operator_lines[0]
    assert not brain._script_queue
