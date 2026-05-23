"""
Unit tests for ``moo.agent.agent_tools`` — one case per tool against a
``FakeConnection`` whose ``request()`` records the dispatched command and
returns a canned response. ``RunContext`` is hand-built per call so the tests
do not exercise PydanticAI's agent loop.

The repo has no pytest-asyncio; coroutine bodies run via ``asyncio.run()``.
"""

# Pylint: pytest fixtures legitimately shadow names and tests legitimately
# probe module-private async-wait patterns to assert dispatch shape.
# pylint: disable=redefined-outer-name,protected-access

import asyncio
import json
import re
from dataclasses import dataclass, field

import pytest
from pydantic_ai import RunContext, Tool
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RunUsage

from moo.agent import agent_tools
from moo.agent.brain.deps import BrainDeps
from moo.agent.brain.state import BrainState


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


@dataclass
class FakeConnection:
    """Records every ``request()`` call; returns a canned response per call."""

    responses: list[str] = field(default_factory=list)
    calls: list[tuple[str, float, re.Pattern | None]] = field(default_factory=list)

    async def request(
        self,
        command: str,
        *,
        async_wait_s: float = 0.0,
        async_pattern: re.Pattern | None = None,
    ) -> str:
        self.calls.append((command, async_wait_s, async_pattern))
        if not self.responses:
            return ""
        return self.responses.pop(0)


class FakeLimiter:
    """Async no-op limiter — ``wait()`` resolves immediately."""

    async def wait(self) -> None:
        return None


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def window() -> list[str]:
    return []


@pytest.fixture
def connection() -> FakeConnection:
    return FakeConnection()


@pytest.fixture
def state() -> BrainState:
    return BrainState(current_room_id="#1", current_room_name="The Agency")


@pytest.fixture
def deps(connection, thoughts, window, state) -> BrainDeps:
    return BrainDeps(
        connection=connection,  # type: ignore[arg-type]
        limiter=FakeLimiter(),  # type: ignore[arg-type]
        soul_name="tester",
        state=state,
        on_thought=thoughts.append,
        on_window_append=window.append,
    )


def make_ctx(deps: BrainDeps) -> RunContext[BrainDeps]:
    """Hand-build a minimal ``RunContext`` for direct tool invocation."""
    return RunContext(deps=deps, model=TestModel(), usage=RunUsage())


def run(coro):
    """Tiny convenience to keep the test bodies one-line."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# World-building tools
# ---------------------------------------------------------------------------


def test_dig_dispatches_with_async_wait(connection, deps, window):
    connection.responses = ["You wave a wand."]
    result = run(agent_tools.dig(make_ctx(deps), "north", "The Library"))
    cmd, wait_s, pattern = connection.calls[0]
    assert cmd == '@dig north to "The Library"'
    assert wait_s == 3.0
    assert pattern is agent_tools._DIG_SUCCESS_RE
    assert result == "You wave a wand."
    assert window == ['> @dig north to "The Library"']


def test_dig_strips_quotes_from_room_name(connection, deps):
    run(agent_tools.dig(make_ctx(deps), "north", '"Already Quoted"'))
    assert connection.calls[0][0] == '@dig north to "Already Quoted"'


def test_go_dispatches_synchronously(connection, deps, window):
    connection.responses = ["The Library"]
    result = run(agent_tools.go(make_ctx(deps), "north"))
    cmd, wait_s, pattern = connection.calls[0]
    assert cmd == "go north"
    assert wait_s == 0.0
    assert pattern is None
    assert result == "The Library"
    assert window == ["> go north"]


def test_describe_normalises_target_and_strips_quotes(connection, deps):
    run(agent_tools.describe(make_ctx(deps), "42", '"A cozy reading nook."'))
    assert connection.calls[0][0] == '@describe #42 as "A cozy reading nook."'


def test_create_object_default_parent(connection, deps):
    run(agent_tools.create_object(make_ctx(deps), "lantern"))
    cmd, wait_s, pattern = connection.calls[0]
    assert cmd == '@create "lantern" from "$thing" in here'
    assert wait_s == 3.0
    assert pattern is agent_tools._CREATE_SUCCESS_RE


def test_create_object_explicit_parent(connection, deps):
    run(agent_tools.create_object(make_ctx(deps), "trunk", "$container"))
    assert connection.calls[0][0] == '@create "trunk" from "$container" in here'


def test_write_verb_assembles_shebang_and_json_payload(connection, deps):
    run(
        agent_tools.write_verb(
            make_ctx(deps),
            obj="42",
            verb="pry",
            code="print('hello')",
            dspec="this",
        )
    )
    cmd, wait_s, pattern = connection.calls[0]
    assert cmd.startswith("@edit verb pry on #42 with ")
    assert wait_s == 3.0
    assert pattern is agent_tools._EDIT_VERB_SUCCESS_RE
    payload = json.loads(cmd.split(" with ", 1)[1])
    assert payload == "#!moo verb pry --on $thing --dspec this\nprint('hello')"


def test_write_verb_honors_custom_on_parent(connection, deps):
    run(
        agent_tools.write_verb(
            make_ctx(deps),
            obj="42",
            verb="enter",
            code="print('through')",
            dspec="any",
            on="$exit",
        )
    )
    payload = json.loads(connection.calls[0][0].split(" with ", 1)[1])
    assert payload == "#!moo verb enter --on $exit --dspec any\nprint('through')"


def test_look_no_target(connection, deps):
    run(agent_tools.look(make_ctx(deps)))
    assert connection.calls[0][0] == "look"


def test_look_with_target_normalises_int(connection, deps):
    run(agent_tools.look(make_ctx(deps), "42"))
    assert connection.calls[0][0] == "look #42"


def test_alias_dispatches_with_async_wait(connection, deps):
    run(agent_tools.alias(make_ctx(deps), "42", "lantern"))
    cmd, wait_s, pattern = connection.calls[0]
    assert cmd == '@alias #42 as "lantern"'
    assert wait_s == 2.0
    assert pattern is agent_tools._ALIAS_SUCCESS_RE


def test_obvious_dispatches_with_async_wait(connection, deps):
    run(agent_tools.obvious(make_ctx(deps), "42"))
    cmd, wait_s, pattern = connection.calls[0]
    assert cmd == "@obvious #42"
    assert wait_s == 2.0
    assert pattern is agent_tools._SET_SUCCESS_RE


def test_move_object(connection, deps):
    run(agent_tools.move_object(make_ctx(deps), "42", "here"))
    assert connection.calls[0][0] == "@move #42 to here"


def test_place(connection, deps):
    run(agent_tools.place(make_ctx(deps), "42", "on", "100"))
    assert connection.calls[0][0] == "place #42 on #100"


def test_open(connection, deps):
    run(agent_tools.open_(make_ctx(deps), "42"))
    assert connection.calls[0][0] == "open #42"


def test_close(connection, deps):
    run(agent_tools.close_(make_ctx(deps), "42"))
    assert connection.calls[0][0] == "close #42"


def test_put(connection, deps):
    run(agent_tools.put(make_ctx(deps), "42", "100"))
    assert connection.calls[0][0] == "put #42 in #100"


def test_take_no_source(connection, deps):
    run(agent_tools.take(make_ctx(deps), "42"))
    assert connection.calls[0][0] == "take #42"


def test_take_with_source(connection, deps):
    run(agent_tools.take(make_ctx(deps), "42", "trunk"))
    assert connection.calls[0][0] == "take #42 from trunk"


def test_drop(connection, deps):
    run(agent_tools.drop(make_ctx(deps), "42"))
    assert connection.calls[0][0] == "drop #42"


def test_tunnel(connection, deps):
    run(agent_tools.tunnel(make_ctx(deps), "south", "19"))
    cmd, wait_s, pattern = connection.calls[0]
    assert cmd == "@tunnel south to #19"
    assert wait_s == 3.0
    assert pattern is agent_tools._DIG_SUCCESS_RE


def test_show_defaults_to_here(connection, deps):
    run(agent_tools.show(make_ctx(deps)))
    assert connection.calls[0][0] == "@show here"


def test_show_with_target(connection, deps):
    run(agent_tools.show(make_ctx(deps), "42"))
    assert connection.calls[0][0] == "@show #42"


def test_survey_no_target(connection, deps):
    run(agent_tools.survey(make_ctx(deps)))
    assert connection.calls[0][0] == "@survey"


def test_survey_with_target(connection, deps):
    run(agent_tools.survey(make_ctx(deps), "42"))
    assert connection.calls[0][0] == "@survey #42"


def test_rooms(connection, deps):
    run(agent_tools.rooms(make_ctx(deps)))
    assert connection.calls[0][0] == "@rooms"


def test_divine_default(connection, deps):
    run(agent_tools.divine(make_ctx(deps)))
    assert connection.calls[0][0] == "@divine location"


def test_divine_with_subject_and_of(connection, deps):
    run(agent_tools.divine(make_ctx(deps), "child", "$thing"))
    assert connection.calls[0][0] == "@divine child of $thing"


def test_exits_defaults_to_here(connection, deps):
    run(agent_tools.exits(make_ctx(deps)))
    assert connection.calls[0][0] == "@exits here"


def test_teleport_normal(connection, deps, state):
    state.current_room_id = "#5"
    state.current_room_name = "The Library"
    run(agent_tools.teleport(make_ctx(deps), "27"))
    assert connection.calls[0][0] == "teleport #27"


def test_teleport_skips_when_already_there_by_id(connection, deps, thoughts, state):
    state.current_room_id = "#27"
    state.current_room_name = "The Greenhouse"
    result = run(agent_tools.teleport(make_ctx(deps), "27"))
    assert connection.calls == []
    assert "Already in The Greenhouse" in result
    assert any("Already in The Greenhouse" in t for t in thoughts)


def test_teleport_skips_when_already_there_by_name(connection, deps, state):
    state.current_room_id = "#27"
    state.current_room_name = "The Greenhouse"
    run(agent_tools.teleport(make_ctx(deps), "The Greenhouse"))
    assert connection.calls == []


def test_teleport_guard_uses_live_state_within_cycle(connection, deps, state):
    """Chained teleports in the same cycle: the second call must see the
    room the first landed in, not the entry-snapshot. Regression test for
    the stale-deps bug fixed by adding ``state`` to ``BrainDeps``."""
    state.current_room_id = "#5"
    state.current_room_name = "The Library"
    connection.responses = ["You arrive at The Greenhouse (#27)."]
    run(agent_tools.teleport(make_ctx(deps), "27"))
    # Brain would normally update state via _update_current_room_from on the
    # tool response side-channel; simulate that here.
    state.current_room_id = "#27"
    state.current_room_name = "The Greenhouse"
    result = run(agent_tools.teleport(make_ctx(deps), "27"))
    assert len(connection.calls) == 1, "second teleport should not dispatch"
    assert "Already in The Greenhouse" in result


def test_burrow(connection, deps):
    run(agent_tools.burrow(make_ctx(deps), "north", "The Loft"))
    cmd, wait_s, pattern = connection.calls[0]
    assert cmd == '@burrow north to "The Loft"'
    assert wait_s == 3.0
    assert pattern is agent_tools._BURROW_SUCCESS_RE


def test_done_marks_session_done_and_skips_dispatch(connection, deps):
    result = run(agent_tools.done(make_ctx(deps), "Built the library wing."))
    assert connection.calls == []
    assert deps.session_done is True
    assert deps.pending_done_msg == "Built the library wing."
    assert "done" in result.lower()


def test_page_dispatches_and_records_token_dispatch(connection, deps, thoughts):
    deps.token_dispatched_at = None
    deps.token_dispatched_to = ""
    run(agent_tools.page(make_ctx(deps), "tinker", "Token: Tinker working in #5 | #7"))
    assert connection.calls[0][0] == "page tinker with Token: Tinker working in #5 | #7"
    assert deps.token_dispatched_to == "tinker"
    assert deps.token_dispatched_at is not None
    assert any("Token dispatched to tinker" in t for t in thoughts)


def test_page_foreman_done_sets_foreman_paged(connection, deps):
    run(agent_tools.page(make_ctx(deps), "foreman", "Token: Stocker done."))
    assert deps.foreman_paged is True
    assert deps.token_dispatched_to == ""


def test_page_non_token_message_does_not_mutate_token_state(connection, deps):
    run(agent_tools.page(make_ctx(deps), "tinker", "hey there"))
    assert deps.token_dispatched_to == ""
    assert deps.token_dispatched_at is None


# ---------------------------------------------------------------------------
# Dispatch Board / Survey Book tools — must auto-teleport to The Agency
# ---------------------------------------------------------------------------


def test_post_board_prefixes_agency_teleport(connection, deps, window):
    connection.responses = ["teleported", "Posted."]
    result = run(agent_tools.post_board(make_ctx(deps), "tradesmen", "#9 | #22 | #37"))
    assert [c[0] for c in connection.calls] == [
        'teleport "The Agency"',
        'post on "The Dispatch Board" under tradesmen with "#9 | #22 | #37"',
    ]
    assert result == "Posted."
    assert window == [
        '> teleport "The Agency"',
        '> post on "The Dispatch Board" under tradesmen with "#9 | #22 | #37"',
    ]


def test_read_board_prefixes_agency_teleport(connection, deps):
    connection.responses = ["teleported", "#9 | #22"]
    result = run(agent_tools.read_board(make_ctx(deps), "tradesmen"))
    assert [c[0] for c in connection.calls] == [
        'teleport "The Agency"',
        'read "The Dispatch Board" under tradesmen',
    ]
    assert result == "#9 | #22"


def test_write_book_prefixes_agency_teleport(connection, deps):
    connection.responses = ["teleported", "Recorded."]
    result = run(agent_tools.write_book(make_ctx(deps), "#9", "tradesmen", "All set.\nNo notes."))
    assert [c[0] for c in connection.calls] == [
        'teleport "The Agency"',
        'write in "The Survey Book" under tradesmen with "#9: All set. No notes."',
    ]
    assert result == "Recorded."


def test_read_book_with_room_id(connection, deps):
    connection.responses = ["teleported", "entry text"]
    run(agent_tools.read_book(make_ctx(deps), "tradesmen", "#9"))
    assert connection.calls[1][0] == 'read "The Survey Book" under tradesmen from #9'


def test_read_book_without_room_id(connection, deps):
    connection.responses = ["teleported", "entry text"]
    run(agent_tools.read_book(make_ctx(deps), "tradesmen"))
    assert connection.calls[1][0] == 'read "The Survey Book" under tradesmen'


def test_clear_topic_erases_board_and_book(connection, deps):
    connection.responses = ["teleported", "board cleared", "book cleared"]
    result = run(agent_tools.clear_topic(make_ctx(deps), "tradesmen"))
    assert [c[0] for c in connection.calls] == [
        'teleport "The Agency"',
        'erase "The Dispatch Board" under tradesmen',
        'erase "The Survey Book" under tradesmen',
    ]
    assert "board cleared" in result and "book cleared" in result


# ---------------------------------------------------------------------------
# System tools
# ---------------------------------------------------------------------------


def test_raw_passes_command_verbatim(connection, deps, window):
    connection.responses = ["OK"]
    result = run(agent_tools.raw(make_ctx(deps), "@realm $room"))
    assert connection.calls[0][0] == "@realm $room"
    assert result == "OK"
    assert window == ["> @realm $room"]


def test_raw_empty_command_returns_empty_without_dispatch(connection, deps):
    result = run(agent_tools.raw(make_ctx(deps), "   "))
    assert connection.calls == []
    assert result == ""


def test_respond_thoughtonly_no_dispatch(connection, deps, thoughts):
    result = run(agent_tools.respond(make_ctx(deps), "Just observing."))
    assert connection.calls == []
    assert "[Respond] Just observing." in thoughts
    assert result == "Acknowledged."
    assert deps.respond_count == 1


def test_respond_empty_message_skips_respond_thought(connection, deps, thoughts):
    result = run(agent_tools.respond(make_ctx(deps), "   "))
    # The "[Tool] respond(...)" call-log thought fires unconditionally; only
    # the "[Respond] <msg>" thought is suppressed when the message is empty.
    assert not any(t.startswith("[Respond]") for t in thoughts)
    assert result == "Acknowledged."


def test_respond_second_call_returns_escalation(connection, deps):
    """The second respond() in one cycle returns a stronger nudge."""
    ctx = make_ctx(deps)
    run(agent_tools.respond(ctx, "first"))
    second = run(agent_tools.respond(ctx, "second"))
    assert deps.respond_count == 2
    assert "twice" in second
    assert "final AgentResponse" in second


def test_respond_third_call_returns_hard_nudge(connection, deps):
    """The third+ respond() call returns the strong 'stop calling respond()' nudge."""
    ctx = make_ctx(deps)
    run(agent_tools.respond(ctx, "first"))
    run(agent_tools.respond(ctx, "second"))
    third = run(agent_tools.respond(ctx, "third"))
    assert deps.respond_count == 3
    assert "Stop calling respond()" in third
    assert "concrete action" in third


# ---------------------------------------------------------------------------
# Registry sanity
# ---------------------------------------------------------------------------


def test_all_tools_has_32_entries():
    assert len(agent_tools.ALL_TOOLS) == 32


def test_all_tools_by_name_keyed_on_advertised_name():
    """``open``/``close`` are wrapped via ``Tool(...)`` to escape the Python
    builtin shadowing; the lookup dict must key on the wrapped name, not the
    function's ``__name__``."""
    assert "open" in agent_tools.ALL_TOOLS_BY_NAME
    assert "close" in agent_tools.ALL_TOOLS_BY_NAME
    assert "open_" not in agent_tools.ALL_TOOLS_BY_NAME
    assert "close_" not in agent_tools.ALL_TOOLS_BY_NAME


def test_select_tools_none_returns_all():
    selected = agent_tools.select_tools(None)
    assert len(selected) == 32


def test_select_tools_filters_to_whitelist_and_appends_system_tools():
    """Whitelisted tools + the always-on raw + respond, in declared order."""
    selected = agent_tools.select_tools(["dig", "go"])
    names = [agent_tools._tool_name(t) for t in selected]
    assert names == ["dig", "go", "raw", "respond"]


def test_select_tools_drops_unknown_silently():
    selected = agent_tools.select_tools(["dig", "frobnicate", "go"])
    names = [agent_tools._tool_name(t) for t in selected]
    assert "frobnicate" not in names
    assert names == ["dig", "go", "raw", "respond"]


def test_select_tools_does_not_duplicate_system_tools():
    """When the whitelist already names raw/respond, they shouldn't appear twice."""
    selected = agent_tools.select_tools(["raw", "page", "respond"])
    names = [agent_tools._tool_name(t) for t in selected]
    assert names.count("raw") == 1
    assert names.count("respond") == 1


# ---------------------------------------------------------------------------
# Live LM Studio regression — tools + ToolOutput coexist on the running model
# ---------------------------------------------------------------------------


@pytest.mark.live_lm_studio
def test_live_lm_studio_tool_loop_dispatches_then_returns_structured_output():
    """
    Full ``agent.run()`` against the local LM Studio endpoint with stub
    ``FakeConnection`` returning canned bracketed responses. Verifies that
    tools fire AND ``r.output`` validates as ``AgentResponse`` — the spike
    result we landed in ``docs/specs/pydantic-ai-stage-2.md``.

    Skipped by default. Enable with ``pytest -m live_lm_studio`` once LM
    Studio is running on ``http://localhost:1234/v1`` with a tool-capable
    model loaded.
    """
    import os
    from types import SimpleNamespace

    from moo.agent.llm_client import make_agent
    from moo.agent.response_model import AgentResponse

    base_url = os.environ.get("LM_STUDIO_URL", "http://localhost:1234/v1")
    model_name = os.environ.get("LM_STUDIO_MODEL", "qwen3.5-9b-mlx")
    llm_cfg = SimpleNamespace(provider="lm_studio", model=model_name, base_url=base_url, api_key_env="")
    agent = make_agent(llm_cfg, "You are a builder agent. Use tools to act.")

    conn = FakeConnection()
    conn.responses = ['Dug an exit north to "Library"']  # canned response for the dig tool
    deps = BrainDeps(
        connection=conn,  # type: ignore[arg-type]
        limiter=FakeLimiter(),  # type: ignore[arg-type]
        soul_name="live-test",
        state=BrainState(current_room_id="#1", current_room_name="Lobby"),
        on_thought=lambda _t: None,
        on_window_append=lambda _l: None,
    )
    result = asyncio.run(
        agent.run(
            "Dig a north exit to a room called Library, then signal done.",
            deps=deps,
        )
    )
    assert isinstance(result.output, AgentResponse)
    assert getattr(result.usage, "tool_calls", 0) >= 1


def test_all_tools_names_match_original_set():
    names = set()
    for t in agent_tools.ALL_TOOLS:
        if isinstance(t, Tool):
            names.add(t.name)
        else:
            names.add(t.__name__)
    expected = {
        "dig",
        "go",
        "describe",
        "create_object",
        "write_verb",
        "look",
        "alias",
        "obvious",
        "move_object",
        "place",
        "open",
        "close",
        "put",
        "take",
        "drop",
        "tunnel",
        "show",
        "survey",
        "rooms",
        "divine",
        "exits",
        "teleport",
        "burrow",
        "done",
        "page",
        "post_board",
        "read_board",
        "write_book",
        "read_book",
        "clear_topic",
        "raw",
        "respond",
    }
    assert names == expected
