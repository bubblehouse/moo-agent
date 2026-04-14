"""
Tests for moo/agent/brain_chain.py — process_server_text pure function.

Covers every branch:
- Orchestrator auto-start on "Connected"
- Worker reconnect page on "Connected" + prior_goal_for_reconnect
- [Mail] line suppression + REPORT: memory_summary injection
- "not currently logged in" clears dispatch timer
- "has connected" triggers re-page
- Dig room ID tracking in rooms_built
- "pages, Token: ... done" triggers orchestrator auto-relay
- "pages, Token: ... reconnected" triggers auto-reconnect
- Worker receives token → check_inbox prepended
- Session state reset on new token when session_done
- Auto-advance plan on dig success
- Plan exhausted flag after last dig
"""

from dataclasses import dataclass

from moo.agent.brain.chain import process_server_text
from moo.agent.brain.state import BrainState
from moo.agent.config import AgentConfig, Config, LLMConfig, SSHConfig


def _make_config(
    user: str = "foreman",
    token_chain: list[str] | None = None,
    idle_wakeup_seconds: float = 0.0,
) -> Config:
    return Config(
        ssh=SSHConfig(host="localhost", port=22, user=user, password="", key_file=""),
        llm=LLMConfig(provider="anthropic", model="test"),
        agent=AgentConfig(
            command_rate_per_second=1.0,
            memory_window_lines=50,
            idle_wakeup_seconds=idle_wakeup_seconds,
            token_chain=token_chain if token_chain is not None else [],
        ),
        soul_path="",  # type: ignore[arg-type]
    )


# --- Orchestrator auto-start ---


def test_connected_orchestrator_auto_pages_first_agent():
    state = BrainState()
    config = _make_config(user="foreman", token_chain=["mason", "tinker"])
    actions = process_server_text("Connected", state, config, now=100.0)
    assert "page mason with Token: Foreman start." in actions.scripts
    assert any("agent of the moment" in s for s in actions.scripts)
    assert state.token_dispatched_to == "mason"
    assert state.token_dispatched_at == 100.0
    assert any("Auto-starting" in t for t in actions.thoughts)


def test_connected_orchestrator_skips_when_token_already_dispatched():
    state = BrainState(token_dispatched_at=50.0, token_dispatched_to="mason")
    config = _make_config(user="foreman", token_chain=["mason", "tinker"])
    actions = process_server_text("Connected", state, config, now=100.0)
    assert not any("Auto-starting" in t for t in actions.thoughts)
    # token_dispatched_at was unchanged
    assert state.token_dispatched_at == 50.0


def test_connected_worker_does_not_auto_start():
    """A worker (user in chain) must not auto-page anyone."""
    state = BrainState()
    config = _make_config(user="mason", token_chain=["mason", "tinker"])
    actions = process_server_text("Connected", state, config, now=100.0)
    assert not actions.scripts
    assert state.token_dispatched_to is None


# --- Worker reconnect on Connected ---


def test_connected_worker_with_prior_goal_reconnects_to_foreman():
    state = BrainState(prior_goal_for_reconnect="explore")
    config = _make_config(user="mason", token_chain=[])
    actions = process_server_text("Connected", state, config, now=100.0)
    assert any("page foreman with Token: Mason reconnected" in s for s in actions.scripts)
    assert state.prior_goal_for_reconnect == ""  # consumed


def test_connected_orchestrator_with_prior_goal_does_not_reconnect():
    state = BrainState(prior_goal_for_reconnect="oversee")
    config = _make_config(user="foreman", token_chain=["mason"])
    actions = process_server_text("Connected", state, config, now=100.0)
    assert not any("Token: Foreman reconnected" in s for s in actions.scripts)
    # Prior goal for reconnect stays set (it's a worker-only consume)
    assert state.prior_goal_for_reconnect == "oversee"


# --- [Mail] suppression ---


def test_mail_line_is_skipped():
    state = BrainState()
    config = _make_config(user="mason", token_chain=[])
    actions = process_server_text("[Mail] You have 0 new messages.", state, config)
    assert actions.skip is True
    assert state.memory_summary == ""


def test_mail_report_injects_memory_summary():
    state = BrainState()
    config = _make_config(user="mason", token_chain=[])
    actions = process_server_text("[Mail] From Foreman: built the library with shelves", state, config)
    assert actions.skip is True
    assert "Foreman" in state.memory_summary
    assert "library" in state.memory_summary
    assert any("Foreman" in t for t in actions.thoughts)


# --- "not currently logged in" / "has connected" re-page ---


def test_not_logged_in_clears_dispatch_timer():
    state = BrainState(token_dispatched_at=50.0, token_dispatched_to="mason")
    config = _make_config(user="foreman", token_chain=["mason"])
    process_server_text("Mason is not currently logged in.", state, config)
    assert state.token_dispatched_at is None
    assert state.token_dispatched_to == "mason"  # target unchanged


def test_has_connected_re_pages_waiting_target():
    state = BrainState(token_dispatched_at=None, token_dispatched_to="mason")
    config = _make_config(user="foreman", token_chain=["mason"])
    actions = process_server_text("Mason has connected.", state, config, now=200.0)
    assert any("page mason with Token: Foreman start." in s for s in actions.scripts)
    assert state.token_dispatched_at == 200.0
    assert any("Re-paging mason" in t for t in actions.thoughts)


def test_has_connected_ignored_when_timer_still_live():
    state = BrainState(token_dispatched_at=50.0, token_dispatched_to="mason")
    config = _make_config(user="foreman", token_chain=["mason"])
    actions = process_server_text("Mason has connected.", state, config, now=200.0)
    assert not actions.scripts
    assert state.token_dispatched_at == 50.0


# --- Dig room ID tracking ---


def test_dig_room_id_tracked_in_rooms_built():
    state = BrainState()
    config = _make_config(user="mason", token_chain=[])
    actions = process_server_text('Dug north to "The Library" (#128)', state, config)
    assert state.rooms_built == ["#128"]
    assert any("#128" in t for t in actions.thoughts)


# --- Token page: session reset ---


def test_token_page_resets_session_done_state():
    state = BrainState(
        session_done=True,
        plan_exhausted=True,
        rooms_built=["#1"],
        foreman_paged=True,
        current_plan=["X"],
    )
    config = _make_config(user="mason", token_chain=[])
    actions = process_server_text("Foreman pages, 'Token: Mason go. Rooms: #89'", state, config)
    assert state.session_done is False
    assert state.plan_exhausted is False
    assert not state.rooms_built
    assert state.foreman_paged is False
    assert state.current_plan == []
    assert actions.save_traversal_plan is True
    assert any("Reset session state" in t for t in actions.thoughts)


def test_token_page_worker_recognizes_go_format():
    """Workers receiving 'Token: X go.' should have session state reset."""
    state = BrainState(session_done=True, foreman_paged=True)
    config = _make_config(user="mason", token_chain=[])
    actions = process_server_text("Foreman pages, 'Token: Mason go.'", state, config)
    assert state.session_done is False
    assert state.foreman_paged is False
    assert any("Reset session state" in t for t in actions.thoughts)


def test_token_done_page_produces_no_prepend_scripts():
    """A done page arriving at the orchestrator should not prepend scripts."""
    state = BrainState()
    config = _make_config(user="foreman", token_chain=["mason"])
    actions = process_server_text("Mason pages, 'Token: Mason done.'", state, config)
    assert not actions.scripts_prepend


def test_token_done_clears_dispatch_timer():
    state = BrainState(token_dispatched_at=50.0, token_dispatched_to="mason")
    config = _make_config(user="foreman", token_chain=["mason", "tinker"])
    actions = process_server_text("Mason pages, 'Token: Mason done.'", state, config)
    # done page clears the live dispatch timer, then auto-relay sets it again
    assert state.token_dispatched_to == "tinker"
    assert any("Stall" in t and "cleared" in t for t in actions.thoughts)


# --- Auto-relay ---


def test_orchestrator_auto_relays_done_to_next_chain_agent():
    state = BrainState(token_dispatched_at=50.0, token_dispatched_to="mason")
    config = _make_config(user="foreman", token_chain=["mason", "tinker", "joiner"])
    actions = process_server_text("Mason pages, 'Token: Mason done.'", state, config, now=300.0)
    assert any("page tinker with Token: Tinker go." in s for s in actions.scripts)
    assert state.token_dispatched_to == "tinker"
    assert state.token_dispatched_at == 300.0
    assert any("Auto-relaying" in t for t in actions.thoughts)


def test_orchestrator_auto_relay_wraps_to_head_of_chain():
    state = BrainState()
    config = _make_config(user="foreman", token_chain=["mason", "tinker"])
    actions = process_server_text("Tinker pages, 'Token: Tinker done.'", state, config, now=300.0)
    assert any("page mason with Token: Mason go." in s for s in actions.scripts)
    assert state.token_dispatched_to == "mason"


def test_worker_does_not_auto_relay():
    """Workers must never relay — they receive tokens, not dispatch them."""
    state = BrainState()
    config = _make_config(user="mason", token_chain=[])
    actions = process_server_text("Foreman pages, 'Token: Mason done.'", state, config)
    assert not any("page" in s and "Token" in s for s in actions.scripts)


# --- Auto-reconnect ---


def test_orchestrator_auto_reconnects_matching_agent():
    state = BrainState(token_dispatched_to="mason", token_dispatched_at=None)
    config = _make_config(user="foreman", token_chain=["mason", "tinker"])
    actions = process_server_text("Mason pages, 'Token: Mason reconnected.'", state, config, now=400.0)
    assert any("page mason with Token: Mason go." in s for s in actions.scripts)
    assert state.token_dispatched_at == 400.0


def test_orchestrator_auto_reconnect_ignored_when_waiting_for_other():
    """If Foreman is currently waiting for Tinker, a Mason reconnect should be ignored."""
    state = BrainState(token_dispatched_to="tinker", token_dispatched_at=50.0)
    config = _make_config(user="foreman", token_chain=["mason", "tinker"])
    actions = process_server_text("Mason pages, 'Token: Mason reconnected.'", state, config, now=400.0)
    assert not any("Token: Mason go." in s for s in actions.scripts)
    assert state.token_dispatched_to == "tinker"  # unchanged


# --- Plan advance on dig success ---


def test_dig_success_advances_plan_past_built_room():
    state = BrainState(current_plan=["The Library", "The Vault", "The Cellar"])
    config = _make_config(user="mason", token_chain=[])
    actions = process_server_text('Dug an exit north to "The Library"', state, config)
    assert state.current_plan == ["The Vault", "The Cellar"]
    assert any("Advanced past" in t for t in actions.thoughts)


def test_dig_success_advances_past_skipped_room():
    """Digging a room deeper in the plan removes preceding rooms."""
    state = BrainState(current_plan=["The Library", "The Vault", "The Cellar"])
    config = _make_config(user="mason", token_chain=[])
    process_server_text('Dug an exit north to "The Cellar"', state, config)
    assert not state.current_plan


def test_dig_success_triggers_plan_exhausted_when_last():
    state = BrainState(current_plan=["The Library"])
    config = _make_config(user="mason", token_chain=[])
    actions = process_server_text('Dug an exit north to "The Library"', state, config)
    assert state.current_plan == []
    assert state.plan_exhausted is True
    assert "BUILD_PLAN fully executed" in state.memory_summary
    assert any("All planned rooms built" in t for t in actions.thoughts)


def test_dig_success_unknown_room_leaves_plan_unchanged():
    state = BrainState(current_plan=["The Library", "The Vault"])
    config = _make_config(user="mason", token_chain=[])
    process_server_text('Dug an exit north to "The Attic"', state, config)
    assert state.current_plan == ["The Library", "The Vault"]


# --- No-op / default ---


def test_plain_text_produces_no_actions():
    state = BrainState()
    config = _make_config(user="mason", token_chain=[])
    actions = process_server_text("You see a room.", state, config)
    assert not actions.scripts
    assert not actions.scripts_prepend
    assert not actions.thoughts
    assert actions.skip is False
    assert actions.save_traversal_plan is False
