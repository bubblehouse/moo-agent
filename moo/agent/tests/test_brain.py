"""
Tests for moo/agent/brain — surviving helper logic plus the new Stage-2 tool
loop wiring. Tests of the deleted ``_dispatch_actions``/``_script_queue``/
``_drain_script``/``_rewrite_board_post``/``_is_redundant_teleport`` paths
have been removed; their behaviour now lives in ``moo/agent/agent_tools.py``
(covered by ``test_agent_tools.py``).
"""
# pylint: disable=protected-access,redefined-outer-name

import asyncio
import re
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Optional
from unittest.mock import AsyncMock, MagicMock

from moo.agent.brain import Brain, Status, looks_like_error
from moo.agent.brain.deps import BrainDeps
from moo.agent.brain.plans import extract_room_names_from_yaml as _extract_room_names_from_yaml
from moo.agent.response_model import AgentResponse
from moo.agent.soul import Rule, Soul, VerbMapping, compile_rules


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class FakeConnection:
    """Records ``send()`` calls; ``request()`` is unused in brain unit tests."""

    def __init__(self):
        self.sent: list[str] = []

    def send(self, cmd: str) -> None:
        self.sent.append(cmd)

    async def request(self, *args, **kwargs):  # pragma: no cover — not exercised here
        return ""


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
    repeat_penalty: float | None = None
    min_p: float | None = None
    structured_output_retries: int = 2
    tool_calls_per_cycle: int = 40
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


def _make_brain(soul=None, config_dir=None, on_status_change=None):
    if soul is None:
        soul = Soul()
    config = _FakeConfig()
    thoughts: list[str] = []
    conn = FakeConnection()
    brain = Brain(
        soul=soul,
        config=config,
        connection=conn,
        on_thought=thoughts.append,
        config_dir=config_dir,
        on_status_change=on_status_change,
    )
    return brain, conn.sent, thoughts


def _agent_response(goal="", *, done=None, soul_patches=None, build_plan=None, plan=None, reasoning=""):
    """Build a validated meta-state ``AgentResponse`` for fake LLM replies."""
    return AgentResponse(
        goal=goal,
        reasoning=reasoning,
        plan=plan,
        done=done,
        soul_patches=soul_patches or [],
        build_plan=build_plan,
    )


def _fake_agent(response: AgentResponse, *, tool_calls: int = 0):
    """
    Mock PydanticAI agent whose ``run()`` yields the given ``AgentResponse``.

    PydanticAI's ``AgentRunResult.usage`` is a property (not a method), so the
    result stub exposes ``usage`` as a plain attribute on a ``SimpleNamespace``.
    """
    agent = MagicMock()
    usage = SimpleNamespace(tool_calls=tool_calls)
    result = SimpleNamespace(output=response, usage=usage)
    agent.run = AsyncMock(return_value=result)
    return agent


# ---------------------------------------------------------------------------
# Rule matching / intent resolution / rule compilation
# ---------------------------------------------------------------------------


def test_check_rules_match():
    soul = Soul(rules=[Rule(pattern="^You feel hungry", command="eat food")])
    brain, _, _ = _make_brain(soul)
    brain._compiled_rules = compile_rules(soul)
    assert brain._check_rules("You feel hungry in the Manor") == "eat food"


def test_check_rules_no_match():
    soul = Soul(rules=[Rule(pattern="^You feel hungry", command="eat food")])
    brain, _, _ = _make_brain(soul)
    brain._compiled_rules = compile_rules(soul)
    assert brain._check_rules("The room is bright and cheerful") is None


def test_check_rules_first_match_wins():
    soul = Soul(
        rules=[
            Rule(pattern="hungry", command="eat food"),
            Rule(pattern="hungry", command="drink water"),
        ]
    )
    brain, _, _ = _make_brain(soul)
    brain._compiled_rules = compile_rules(soul)
    assert brain._check_rules("You feel hungry") == "eat food"


def test_resolve_intent_known():
    soul = Soul(verb_mappings=[VerbMapping(intent="look_around", template="look")])
    brain, _, _ = _make_brain(soul)
    assert brain._resolve_intent("look_around") == "look"


def test_resolve_intent_case_insensitive():
    soul = Soul(verb_mappings=[VerbMapping(intent="Look_Around", template="look")])
    brain, _, _ = _make_brain(soul)
    assert brain._resolve_intent("look_around") == "look"


def test_resolve_intent_unknown_passthrough():
    soul = Soul()
    brain, _, _ = _make_brain(soul)
    assert brain._resolve_intent("go north") == "go north"


def test_compile_rules_empty():
    assert compile_rules(Soul()) == []


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
    assert not pattern0.search("  hungry now")


# ---------------------------------------------------------------------------
# Soul patches
# ---------------------------------------------------------------------------


def test_apply_patch_updates_rules(tmp_path):
    (tmp_path / "SOUL.md").write_text("# Name\nTest\n# Mission\nM\n# Persona\nP\n")
    brain, _, _ = _make_brain(Soul(), config_dir=tmp_path)
    brain._apply_patch("rule", "^You are thirsty -> drink water")
    assert any(r.pattern == "^You are thirsty" for r in brain._soul.rules)


def test_apply_patch_bad_directive_ignored(tmp_path):
    (tmp_path / "SOUL.md").write_text("# Name\nTest\n# Mission\nM\n# Persona\nP\n")
    brain, _, _ = _make_brain(Soul(), config_dir=tmp_path)
    brain._apply_patch("rule", "no arrow here")
    assert brain._soul.rules == []


def test_apply_patch_no_config_dir_noop():
    brain, _, _ = _make_brain(Soul(), config_dir=None)
    brain._apply_patch("rule", "trigger -> command")
    assert brain._soul.rules == []


def test_apply_patch_note_written_to_file(tmp_path):
    (tmp_path / "SOUL.md").write_text("# Name\nTest\n# Mission\nM\n# Persona\nP\n")
    brain, _, _ = _make_brain(Soul(), config_dir=tmp_path)
    brain._apply_patch("note", "obj.name is a model field — always call obj.save()")
    text = (tmp_path / "SOUL.patch.md").read_text()
    assert "obj.name is a model field" in text
    assert "## Lessons Learned" in text


def test_apply_patch_note_no_arrow_required(tmp_path):
    (tmp_path / "SOUL.md").write_text("# Name\nTest\n# Mission\nM\n# Persona\nP\n")
    brain, _, _ = _make_brain(Soul(), config_dir=tmp_path)
    brain._apply_patch("note", "plain note with no arrow")
    text = (tmp_path / "SOUL.patch.md").read_text()
    assert "plain note with no arrow" in text


def test_apply_patch_note_reloads_context(tmp_path):
    (tmp_path / "SOUL.md").write_text("# Name\nTest\n# Mission\nM\n# Persona\nP\n")
    brain, _, _ = _make_brain(Soul(), config_dir=tmp_path)
    brain._apply_patch("note", "Always check exits before digging")
    assert "Always check exits before digging" in brain._soul.context


def test_llm_cycle_applies_soul_patch_note(tmp_path):
    """A soul_patches entry in the AgentResponse is appended to SOUL.patch.md."""
    (tmp_path / "SOUL.md").write_text("# Name\nTest\n# Mission\nM\n# Persona\nP\n")
    brain, _, _ = _make_brain(Soul(), config_dir=tmp_path)
    brain._agent = _fake_agent(
        _agent_response(
            goal="continue",
            soul_patches=[{"kind": "note", "content": "obj.name needs obj.save() to persist"}],
        ),
        tool_calls=1,
    )
    asyncio.run(brain._llm_cycle())
    assert "obj.name needs obj.save()" in (tmp_path / "SOUL.patch.md").read_text()


# ---------------------------------------------------------------------------
# Status / on_status_change
# ---------------------------------------------------------------------------


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
    brain._set_status(Status.READY)  # already READY at start
    assert not events


def test_set_status_sequences():
    events = []
    brain, _, _ = _make_brain(on_status_change=events.append)
    brain._set_status(Status.THINKING)
    brain._set_status(Status.THINKING)
    brain._set_status(Status.READY)
    assert events == [Status.THINKING, Status.READY]


# ---------------------------------------------------------------------------
# Output ingestion + initial state
# ---------------------------------------------------------------------------


def test_enqueue_output_resets_activity_time():
    import time

    brain, _, _ = _make_brain()
    old_time = brain._last_activity
    time.sleep(0.01)
    brain.enqueue_output("hello")
    assert brain._last_activity > old_time


def test_initial_goal_and_plan_empty():
    brain, _, _ = _make_brain()
    assert brain._state.current_goal == ""
    assert not brain._state.current_plan
    assert brain._state.memory_summary == ""


# ---------------------------------------------------------------------------
# User-message builder
# ---------------------------------------------------------------------------


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
    assert "Current goal: find the brass key" in brain._build_user_message()


def test_build_user_message_includes_plan():
    brain, _, _ = _make_brain()
    brain._state.current_plan = ["go north", "look", "take key"]
    brain._window.append("You are in the Great Hall.")
    assert "Remaining plan: go north | look | take key" in brain._build_user_message()


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
    assert msg.index("Earlier summary") < msg.index("Current goal")
    assert msg.index("Current goal") < msg.index("Remaining plan")
    assert msg.index("Remaining plan") < msg.index("Room output")


def test_build_user_message_no_wakeup_counter_at_zero():
    brain, _, _ = _make_brain()
    brain._state.idle_wakeup_count = 0
    brain._window.append("You are in the Great Hall.")
    assert "Idle wakeup" not in brain._build_user_message()


def test_build_user_message_includes_wakeup_counter():
    brain, _, _ = _make_brain()
    brain._state.idle_wakeup_count = 5
    brain._window.append("You are in the Great Hall.")
    assert "[Idle wakeups since last server output: 5]" in brain._build_user_message()


def test_build_user_message_wakeup_counter_before_window():
    brain, _, _ = _make_brain()
    brain._state.idle_wakeup_count = 3
    brain._window.append("Room output here.")
    msg = brain._build_user_message()
    assert msg.index("Idle wakeups") < msg.index("Room output here")


# ---------------------------------------------------------------------------
# looks_like_error
# ---------------------------------------------------------------------------


def testlooks_like_error_true():
    assert looks_like_error("Error: verb not found")
    assert looks_like_error("TypeError: expected str")
    assert looks_like_error("Traceback (most recent call last):")
    assert looks_like_error("  Error: leading whitespace")


def testlooks_like_error_false():
    assert not looks_like_error("Room created successfully.")
    assert not looks_like_error("Description set.")
    assert not looks_like_error("")


# ---------------------------------------------------------------------------
# Session done blocks LLM cycle dispatch
# ---------------------------------------------------------------------------


def test_session_done_blocks_output_wakeup():
    """After done is signalled, enqueue_output must not trigger a new LLM cycle."""
    brain, sent, thoughts = _make_brain()
    brain._state.session_done = True
    brain._state.current_goal = ""

    async def _run_one_cycle():
        brain.enqueue_output("Flicker says: Is it Tuesday?")
        task = asyncio.ensure_future(brain.run())
        await asyncio.sleep(0.35)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(_run_one_cycle())
    assert not sent
    assert not any("LLM" in t or "cycle" in t.lower() for t in thoughts)


# ---------------------------------------------------------------------------
# LLM-cycle metadata: goal, plan, done, build_plan, soul_patches
# ---------------------------------------------------------------------------


def test_llm_cycle_done_field_clears_goal():
    """The legacy ``done`` field clears the goal when foreman has been paged."""
    brain, _, _ = _make_brain()
    brain._state.current_goal = "survey"
    brain._state.foreman_paged = True
    brain._agent = _fake_agent(_agent_response(goal="survey", done="Surveyed the area."), tool_calls=1)
    asyncio.run(brain._llm_cycle())
    assert brain._state.pending_done_msg == "Surveyed the area."
    assert brain._state.session_done is True
    assert brain._state.current_goal == ""


def test_llm_cycle_done_field_blocked_without_foreman_page():
    brain, _, thoughts = _make_brain()
    brain._state.current_goal = "build the library"
    brain._state.foreman_paged = False
    brain._agent = _fake_agent(_agent_response(goal="build the library", done="Library built."), tool_calls=1)
    asyncio.run(brain._llm_cycle())
    assert "page" in brain._state.current_goal and "foreman" in brain._state.current_goal
    assert not brain._state.session_done
    assert any("Blocked" in t for t in thoughts)


def test_llm_cycle_emits_pending_done_msg_at_start():
    """Pending done message emitted at the start of the next ``_llm_cycle``."""
    brain, _, thoughts = _make_brain()
    brain._state.pending_done_msg = "Script finished."
    brain._agent = _fake_agent(_agent_response(goal="next"), tool_calls=1)
    asyncio.run(brain._llm_cycle())
    assert any("Script finished." in t for t in thoughts)
    assert brain._state.pending_done_msg == ""


def test_llm_cycle_plan_field_sets_current_plan():
    brain, _, _ = _make_brain()
    brain._agent = _fake_agent(_agent_response(goal="traverse", plan=["#9", "#22", "#37"]), tool_calls=1)
    asyncio.run(brain._llm_cycle())
    assert brain._state.current_plan == ["#9", "#22", "#37"]


def test_llm_cycle_null_plan_leaves_current_plan_untouched():
    brain, _, _ = _make_brain()
    brain._state.current_plan = ["#1", "#2"]
    brain._agent = _fake_agent(_agent_response(goal="work"), tool_calls=1)
    asyncio.run(brain._llm_cycle())
    assert brain._state.current_plan == ["#1", "#2"]


# ---------------------------------------------------------------------------
# BUILD_PLAN / _save_build_plan
# ---------------------------------------------------------------------------


def test_save_build_plan_creates_yaml_file(tmp_path):
    brain, _, thoughts = _make_brain(config_dir=tmp_path)
    brain._save_build_plan("phase: Test\\nrooms:\\n  - Room A")
    builds_dir = tmp_path / "builds"
    assert builds_dir.exists()
    files = list(builds_dir.glob("*.yaml"))
    assert len(files) == 1
    assert any("[Build Plan]" in t for t in thoughts)


def test_save_build_plan_expands_newlines(tmp_path):
    brain, _, _ = _make_brain(config_dir=tmp_path)
    brain._save_build_plan("phase: Test\\nrooms:\\n  - Room A")
    files = list((tmp_path / "builds").glob("*.yaml"))
    content = files[0].read_text()
    assert "phase: Test\n" in content
    assert "  - Room A" in content


def test_save_build_plan_no_config_dir_is_noop():
    brain, _, _ = _make_brain(config_dir=None)
    brain._save_build_plan("phase: Test")


def test_llm_cycle_handles_build_plan_field(tmp_path):
    (tmp_path / "SOUL.md").write_text("# Name\nTest\n# Mission\nM\n# Persona\nP\n")
    brain, _, _ = _make_brain(Soul(), config_dir=tmp_path)
    brain._agent = _fake_agent(
        _agent_response(goal="build phase", build_plan='phase: "Acid Wing"\nrooms:\n  - The Acid Bath'),
        tool_calls=1,
    )
    asyncio.run(brain._llm_cycle())
    builds_dir = tmp_path / "builds"
    assert builds_dir.exists()
    files = list(builds_dir.glob("*.yaml"))
    assert len(files) == 1
    content = files[0].read_text()
    assert "Acid Wing" in content
    assert "The Acid Bath" in content


# ---------------------------------------------------------------------------
# Stage-2: ``BrainDeps`` fold-back from side-effecting tools
# ---------------------------------------------------------------------------


def test_make_deps_exposes_live_state():
    brain, _, _ = _make_brain()
    brain._state.current_room_id = "#42"
    brain._state.current_room_name = "Vault"
    deps = brain._make_deps()
    assert isinstance(deps, BrainDeps)
    # ``deps.state`` is the same object Brain mutates — reads inside a tool
    # see mid-cycle room changes (regression fix for the teleport guard).
    assert deps.state is brain._state
    assert deps.state.current_room_id == "#42"
    assert deps.state.current_room_name == "Vault"
    assert deps.connection is brain._connection
    assert deps.limiter is brain._limiter


def test_apply_agent_response_folds_back_token_dispatch():
    brain, _, _ = _make_brain()
    deps = brain._make_deps()
    deps.token_dispatched_to = "tinker"
    deps.token_dispatched_at = 12345.0
    brain._apply_agent_response(_agent_response(goal="hand off"), deps)
    assert brain._state.token_dispatched_to == "tinker"
    assert brain._state.token_dispatched_at == 12345.0


def test_apply_agent_response_folds_back_foreman_paged():
    brain, _, _ = _make_brain()
    deps = brain._make_deps()
    deps.foreman_paged = True
    brain._apply_agent_response(_agent_response(goal="signal"), deps)
    assert brain._state.foreman_paged is True


def test_apply_agent_response_session_done_via_deps_runs_through_handle_done():
    brain, _, _ = _make_brain()
    brain._state.foreman_paged = True  # bypass the foreman-paged guard
    deps = brain._make_deps()
    deps.session_done = True
    deps.pending_done_msg = "All wrapped up."
    brain._apply_agent_response(_agent_response(goal="finalise"), deps)
    assert brain._state.session_done is True
    assert brain._state.pending_done_msg == "All wrapped up."


def test_record_tool_dispatch_logs_to_window_and_action_callback():
    actions: list[str] = []

    @dataclass
    class _Fake:
        pass

    config = _FakeConfig()
    conn = FakeConnection()
    brain = Brain(
        soul=Soul(),
        config=config,
        connection=conn,
        on_thought=lambda _: None,
        on_action_sent=actions.append,
    )
    brain._record_tool_dispatch("> @dig north")
    assert brain._window[-1] == "> @dig north"
    assert actions == ["@dig north"]


# ---------------------------------------------------------------------------
# Cycle stats marker
# ---------------------------------------------------------------------------


def test_llm_cycle_emits_cycle_marker():
    brain, _, thoughts = _make_brain()
    # Skip the worker auto-recycle so the cycle emits exactly one marker.
    brain._state.foreman_paged = True
    brain._agent = _fake_agent(_agent_response(goal="build the library"), tool_calls=1)
    asyncio.run(brain._llm_cycle())
    cycle_lines = [t for t in thoughts if t.startswith("[Cycle]")]
    assert len(cycle_lines) == 1
    line = cycle_lines[0]
    assert "duration=" in line
    assert "tool_calls=1" in line
    assert "outcome=dispatched" in line


def test_productive_worker_cycle_schedules_auto_recycle():
    """A worker cycle that ends with tool calls but without paging foreman
    done must auto-fire another cycle — otherwise the LLM stops mid-mission
    after one or two tool calls and the chain stalls until Foreman's stall
    timer fires. Tool responses go through the side channel so they don't
    trigger ``pending_llm`` — the auto-recycle is the only path forward."""
    brain, _, thoughts = _make_brain()
    # Worker state: token in hand, mid-mission, hasn't paged done yet.
    brain._state.foreman_paged = False
    brain._state.session_done = False
    brain._is_orchestrator = False
    brain._agent = _fake_agent(_agent_response(goal="building shelves"), tool_calls=2)
    asyncio.run(brain._llm_cycle())
    cycle_lines = [t for t in thoughts if t.startswith("[Cycle]")]
    # First cycle's marker + the auto-recycled second cycle's marker. The
    # second cycle also increments the counter (and would schedule a third
    # if the cap allowed), so recycle_count == 2 after the chain settles.
    assert len(cycle_lines) == 2
    assert brain._state.recycle_count >= 1


def test_worker_cycle_after_done_does_not_recycle():
    """Once the worker has paged foreman done, no more auto-recycles."""
    brain, _, thoughts = _make_brain()
    brain._state.foreman_paged = True
    brain._state.session_done = False
    brain._is_orchestrator = False
    brain._agent = _fake_agent(_agent_response(goal="building shelves"), tool_calls=2)
    asyncio.run(brain._llm_cycle())
    cycle_lines = [t for t in thoughts if t.startswith("[Cycle]")]
    assert len(cycle_lines) == 1


def test_productive_cycle_resets_empty_cycle_budget():
    """A productive cycle clears empty_cycle_count so a *later* zero-action
    cycle in the same task gets a fresh 3-cycle nudge window.

    Regression: the previous goal_only_count overload meant a productive
    cycle incrementing the counter towards the recycle cap *also* burned
    the empty-cycle budget — so an agent that built a few things then
    paused would skip straight to the escalation nudge."""
    brain, _, thoughts = _make_brain()
    brain._state.foreman_paged = True
    brain._is_orchestrator = False
    brain._state.empty_cycle_count = 2  # left from a prior zero-action burst
    brain._agent = _fake_agent(_agent_response(goal="building shelves"), tool_calls=2)
    asyncio.run(brain._llm_cycle())
    assert brain._state.empty_cycle_count == 0
    # No premature "Three empty cycles" nudge in the rolling window.
    assert not any("[Operator]" in t and "no tool calls" in t for t in thoughts)


def test_llm_cycle_marker_records_zero_tool_calls_as_goal_only():
    brain, _, thoughts = _make_brain()
    # Skip the recycle gate so the cycle emits exactly one marker.
    brain._state.plan_exhausted = True
    brain._agent = _fake_agent(_agent_response(goal="thinking"), tool_calls=0)
    asyncio.run(brain._llm_cycle())
    cycle_lines = [t for t in thoughts if t.startswith("[Cycle]")]
    assert len(cycle_lines) == 1
    line = cycle_lines[0]
    assert "tool_calls=0" in line
    assert "outcome=goal_only" in line


def test_llm_cycle_marker_emitted_on_llm_error():
    brain, _, thoughts = _make_brain()

    async def _boom(*args, **kwargs):
        raise RuntimeError("llm unreachable")

    brain._agent = MagicMock()
    brain._agent.run = _boom

    asyncio.run(brain._llm_cycle())
    cycle_lines = [t for t in thoughts if t.startswith("[Cycle]")]
    assert len(cycle_lines) == 1
    assert "tool_calls=0" in cycle_lines[0]
    assert "outcome=goal_only" in cycle_lines[0]


def test_run_llm_with_retry_maps_validation_failure_to_none():
    from pydantic_ai.exceptions import UnexpectedModelBehavior

    brain, _, thoughts = _make_brain()

    async def _retry_exhausted(*args, **kwargs):
        raise UnexpectedModelBehavior("validation failed")

    brain._agent = MagicMock()
    brain._agent.run = _retry_exhausted

    result = asyncio.run(brain._run_llm_with_retry("user", brain._make_deps()))
    assert result is None
    assert any("structured-output validation failed" in t for t in thoughts)


def test_run_llm_with_retry_maps_usage_limit_exceeded_to_none():
    """A ``UsageLimitExceeded`` from the tool-call cap surfaces as None and
    emits a ``[Cycle] tool_call_cap_hit`` thought so the recycle path fires."""
    from pydantic_ai.exceptions import UsageLimitExceeded

    brain, _, thoughts = _make_brain()

    async def _cap_hit(*args, **kwargs):
        raise UsageLimitExceeded("would exceed tool_calls_limit of 20")

    brain._agent = MagicMock()
    brain._agent.run = _cap_hit

    result = asyncio.run(brain._run_llm_with_retry("user", brain._make_deps()))
    assert result is None
    assert any("tool_call_cap_hit" in t for t in thoughts)


# ---------------------------------------------------------------------------
# Stall check (adaptive cycle-age threshold)
# ---------------------------------------------------------------------------


def _fake_subprocess_exec(stdout_bytes: bytes, returncode: int = 0):
    class _FakeProc:
        def __init__(self):
            self.returncode = returncode

        async def communicate(self):
            return stdout_bytes, b""

    async def _exec(*args, **kwargs):
        return _FakeProc()

    return _exec


def test_stall_check_skips_repage_when_target_is_actively_cycling(monkeypatch):
    monkeypatch.setenv("MOO_TOKEN_CHAIN_GROUP", "tradesmen")
    monkeypatch.setenv("MOO_AGENTMUX_PATH", "/fake/agentmux")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_subprocess_exec(b"120 150.0\n", 0))
    brain, _, thoughts = _make_brain()
    assert asyncio.run(brain._target_is_actively_cycling("tinker", 60)) is True
    skip_lines = [t for t in thoughts if "still cycling" in t]
    assert len(skip_lines) == 1
    assert "tinker" in skip_lines[0]
    assert "elapsed=120s" in skip_lines[0]
    assert "3×p95=450s" in skip_lines[0]


def test_stall_check_repages_when_target_exceeds_adaptive_threshold(monkeypatch):
    monkeypatch.setenv("MOO_TOKEN_CHAIN_GROUP", "tradesmen")
    monkeypatch.setenv("MOO_AGENTMUX_PATH", "/fake/agentmux")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_subprocess_exec(b"500 100.0\n", 0))
    brain, _, thoughts = _make_brain()
    assert asyncio.run(brain._target_is_actively_cycling("tinker", 60)) is False
    assert not [t for t in thoughts if "still cycling" in t]


def test_stall_check_falls_through_when_env_vars_missing(monkeypatch):
    monkeypatch.delenv("MOO_TOKEN_CHAIN_GROUP", raising=False)
    monkeypatch.delenv("MOO_AGENTMUX_PATH", raising=False)
    called = {"count": 0}

    async def _should_not_be_called(*args, **kwargs):
        called["count"] += 1
        raise AssertionError("subprocess should not be invoked")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _should_not_be_called)
    brain, _, thoughts = _make_brain()
    assert asyncio.run(brain._target_is_actively_cycling("tinker", 60)) is False
    assert called["count"] == 0
    assert not [t for t in thoughts if "still cycling" in t]


def test_stall_check_falls_through_on_subprocess_failure(monkeypatch):
    monkeypatch.setenv("MOO_TOKEN_CHAIN_GROUP", "tradesmen")
    monkeypatch.setenv("MOO_AGENTMUX_PATH", "/fake/agentmux")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_subprocess_exec(b"", 2))
    brain, _, thoughts = _make_brain()
    assert asyncio.run(brain._target_is_actively_cycling("tinker", 60)) is False
    assert not [t for t in thoughts if "still cycling" in t]


def test_stall_check_falls_through_on_sentinel_values(monkeypatch):
    monkeypatch.setenv("MOO_TOKEN_CHAIN_GROUP", "tradesmen")
    monkeypatch.setenv("MOO_AGENTMUX_PATH", "/fake/agentmux")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_subprocess_exec(b"-1 -1.0\n", 0))
    brain, _, thoughts = _make_brain()
    assert asyncio.run(brain._target_is_actively_cycling("tinker", 60)) is False
    assert not [t for t in thoughts if "still cycling" in t]


def test_stall_check_honors_minimum_of_configured_timeout(monkeypatch):
    monkeypatch.setenv("MOO_TOKEN_CHAIN_GROUP", "tradesmen")
    monkeypatch.setenv("MOO_AGENTMUX_PATH", "/fake/agentmux")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_subprocess_exec(b"200 10.0\n", 0))
    brain, _, thoughts = _make_brain()
    assert asyncio.run(brain._target_is_actively_cycling("tinker", 300)) is True
    skip_lines = [t for t in thoughts if "still cycling" in t]
    assert len(skip_lines) == 1
    assert "elapsed=200s" in skip_lines[0]


# ---------------------------------------------------------------------------
# Current-room parsing
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Verb-test mistake detector
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# YAML helpers (kept for completeness)
# ---------------------------------------------------------------------------


def test_extract_room_names_from_yaml_unquoted():
    yaml = "rooms:\n  - name: The Library\n  - name: The Vault\n"
    assert _extract_room_names_from_yaml(yaml) == ["The Library", "The Vault"]


def test_extract_room_names_from_yaml_quoted():
    yaml = "rooms:\n  - name: \"The Acid Bath\"\n  - name: 'The Boneyard'\n"
    assert _extract_room_names_from_yaml(yaml) == ["The Acid Bath", "The Boneyard"]


def test_extract_room_names_from_yaml_empty():
    assert _extract_room_names_from_yaml("phase: Build\n") == []


def test_extract_room_names_excludes_nested():
    yaml = "rooms:\n  - name: The Library\n    objects:\n      - name: A Shelf\n"
    assert _extract_room_names_from_yaml(yaml) == ["The Library"]


# ---------------------------------------------------------------------------
# Save-plan error handling
# ---------------------------------------------------------------------------


def test_save_build_plan_oserror_does_not_raise(tmp_path):
    brain, _, thoughts = _make_brain(config_dir=tmp_path)
    (tmp_path / "builds").write_text("not a dir")
    brain._save_build_plan("phase: Test\\nrooms:\\n  - name: The Lab")
    assert any("Error saving" in t for t in thoughts)


def test_save_traversal_plan_oserror_does_not_raise(tmp_path):
    brain, _, thoughts = _make_brain(config_dir=tmp_path)
    brain._state.current_plan = ["The Library", "The Vault"]
    (tmp_path / "builds").write_text("not a dir")
    brain._save_traversal_plan()
    assert any("Error saving" in t for t in thoughts)
