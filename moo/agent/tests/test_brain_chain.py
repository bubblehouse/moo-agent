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
    assert "page mason with Token: Mason go." in actions.scripts
    assert not any("agent of the moment" in s for s in actions.scripts)
    assert state.token_dispatched_to == "mason"
    assert state.token_dispatched_at == 100.0
    assert any("Auto-starting" in t for t in actions.thoughts)


def test_connected_orchestrator_repages_holder_when_dispatch_restored():
    """When dispatch.json restored a holder, Foreman re-pages them on boot —
    the worker often restarted with us and needs a fresh ``Token: X go.``
    signal. Skipping the page leaves the worker idle indefinitely."""
    state = BrainState(token_dispatched_at=50.0, token_dispatched_to="mason")
    config = _make_config(user="foreman", token_chain=["mason", "tinker"])
    actions = process_server_text("Connected", state, config, now=100.0)
    assert not any("Auto-starting" in t for t in actions.thoughts)
    assert "page mason with Token: Mason go." in actions.scripts
    assert state.token_dispatched_at == 100.0
    assert state.token_dispatched_to == "mason"
    assert actions.save_dispatch_state is True
    assert any("Resuming" in t and "re-paging mason" in t for t in actions.thoughts)


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
    assert any("page mason with Token: Mason go." in s for s in actions.scripts)
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


# --- Auto-plan extraction from divine() output ---


def test_divine_output_auto_populates_current_plan():
    """Server's divine() listing populates current_plan without an LLM PLAN: directive.

    Gemma reliably stalls when asked to transform divine output into a PLAN:
    directive. Auto-extraction lets the agent skip that step entirely.
    """
    state = BrainState()
    config = _make_config(user="stocker", token_chain=[])
    text = (
        "Impressions surface from the noise of the world (3):\n"
        "  Wine Undercroft (#124)\n"
        "  Coal Storage (#273)\n"
        "  Steam Manifold (#208)"
    )
    actions = process_server_text(text, state, config)
    assert state.current_plan == ["#124", "#273", "#208"]
    assert actions.save_traversal_plan is True
    assert any("Auto-Plan" in t and "3 rooms" in t for t in actions.thoughts)


def test_divine_output_does_not_overwrite_active_plan():
    """Plan auto-extraction must defer to an existing token-page or BUILD_PLAN: plan."""
    state = BrainState(current_plan=["Library", "Kitchen"])
    config = _make_config(user="stocker", token_chain=[])
    text = "Impressions surface from the noise of the world (1):\n  Some Room (#999)"
    actions = process_server_text(text, state, config)
    assert state.current_plan == ["Library", "Kitchen"]
    assert not any("Auto-Plan" in t for t in actions.thoughts)


def test_divine_output_overrides_stale_plan_from_disk():
    """A plan loaded from disk on startup is stale; divine output should replace it."""
    state = BrainState(current_plan=["#1", "#2"], plan_from_disk=True)
    config = _make_config(user="stocker", token_chain=[])
    text = "Impressions surface from the noise of the world (2):\n  A (#10)\n  B (#20)"
    process_server_text(text, state, config)
    assert state.current_plan == ["#10", "#20"]
    assert state.plan_from_disk is False


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


def test_token_heartbeat_clears_dispatch_timer():
    """A non-done ``Token: X working.`` page from the current holder also
    clears Foreman's stall timer. Without this the worker gets stall-paged
    every 180s while making real progress and tends to surrender the token."""
    state = BrainState(token_dispatched_at=50.0, token_dispatched_to="tinker")
    config = _make_config(user="foreman", token_chain=["mason", "tinker"])
    actions = process_server_text("Tinker pages, 'Token: Tinker working.'", state, config)
    assert state.token_dispatched_at is None
    # Holder is unchanged — Tinker still owns the token after a heartbeat.
    assert state.token_dispatched_to == "tinker"
    # No auto-relay on a heartbeat — that fires only on done.
    assert not any("page mason with Token:" in s or "page tinker with Token:" in s for s in actions.scripts)
    assert any("Heartbeat" in t and "cleared" in t for t in actions.thoughts)


def test_token_page_from_non_holder_does_not_clear_timer():
    """A ``Token:`` page from someone other than the current holder must not
    reset the stall timer — otherwise a stray worker page could mask a
    genuine stall on the actual holder."""
    state = BrainState(token_dispatched_at=50.0, token_dispatched_to="tinker")
    config = _make_config(user="foreman", token_chain=["mason", "tinker"])
    # Mason pages something with Token: while tinker holds the token.
    process_server_text("Mason pages, 'Token: Mason reconnected.'", state, config)
    assert state.token_dispatched_at == 50.0  # timer untouched


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


def test_orchestrator_auto_reconnects_with_site_suffix():
    """Multi-universe SSH users include a +site suffix in their reconnect page."""
    state = BrainState(token_dispatched_to="stocker", token_dispatched_at=None)
    config = _make_config(user="foreman", token_chain=["mason", "stocker"])
    actions = process_server_text(
        "Stocker pages, 'Token: Stocker+bijaz.local reconnected.'",
        state,
        config,
        now=400.0,
    )
    assert any("page stocker with Token: Stocker go." in s for s in actions.scripts)
    assert state.token_dispatched_at == 400.0
    assert state.token_dispatched_to == "stocker"


def test_worker_reconnect_page_strips_site_suffix():
    """A worker logged in as user+site should still page foreman as just <Name>."""
    state = BrainState(prior_goal_for_reconnect="resume")
    config = _make_config(user="stocker+bijaz.local", token_chain=[])
    actions = process_server_text("Connected", state, config, now=100.0)
    assert any("page foreman with Token: Stocker reconnected." in s for s in actions.scripts)
    assert not any("+bijaz" in s for s in actions.scripts)


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


# --- Worker disconnect arms re-page on reconnect ---


def test_worker_disconnect_clears_dispatch_timer():
    """A worker's disconnect must clear ``token_dispatched_at`` so the next
    ``has connected`` event triggers an automatic re-page. Without this, a
    fast disconnect/reconnect leaves the timer live from the prior heartbeat
    and the connect handler short-circuits — the worker reconnects but
    never receives the token again until the stall timer fires."""
    state = BrainState(token_dispatched_at=50.0, token_dispatched_to="mason")
    config = _make_config(user="foreman", token_chain=["mason", "tinker"])
    actions = process_server_text("#643 (Mason) has disconnected.", state, config, now=200.0)
    assert state.token_dispatched_at is None
    assert state.token_dispatched_to == "mason"
    assert state.last_reconnect_repage_at is None  # fresh session
    assert any("disconnected" in t and "armed for re-page" in t for t in actions.thoughts)


def test_worker_disconnect_for_non_holder_is_noop():
    """Disconnect events for someone other than the current holder must not
    touch Foreman's stall timer."""
    state = BrainState(token_dispatched_at=50.0, token_dispatched_to="mason")
    config = _make_config(user="foreman", token_chain=["mason", "tinker"])
    process_server_text("#644 (Tinker) has disconnected.", state, config, now=200.0)
    assert state.token_dispatched_at == 50.0


def test_disconnect_followed_by_reconnect_triggers_re_page():
    """End-to-end: disconnect arms; reconnect fires the deterministic re-page."""
    state = BrainState(token_dispatched_at=50.0, token_dispatched_to="mason")
    config = _make_config(user="foreman", token_chain=["mason", "tinker"])
    process_server_text("#643 (Mason) has disconnected.", state, config, now=200.0)
    actions = process_server_text("#643 (Mason) has connected.", state, config, now=205.0)
    assert any("page mason with Token: Mason go." in s for s in actions.scripts)
    assert state.token_dispatched_at == 205.0


# --- Reconnect re-page cooldown ---


def test_auto_reconnect_repage_cooldown_blocks_rapid_followups():
    """After Foreman re-pages a worker via auto-reconnect, subsequent
    ``Token: X reconnected`` pages within the cooldown window must be
    ignored — otherwise a chatty LLM that pings Foreman 5 times in 30s
    yields 5 re-pages and the original loop returns."""
    state = BrainState(token_dispatched_to="mason", token_dispatched_at=None)
    config = _make_config(user="foreman", token_chain=["mason", "tinker"])

    # First reconnect: re-pages and arms the cooldown.
    actions1 = process_server_text("Mason pages, 'Token: Mason reconnected.'", state, config, now=400.0)
    assert any("Token: Mason go." in s for s in actions1.scripts)
    assert state.last_reconnect_repage_at == 400.0

    # Second reconnect within cooldown: ignored.
    actions2 = process_server_text("Mason pages, 'Token: Mason reconnected.'", state, config, now=410.0)
    assert not any("page mason with Token:" in s for s in actions2.scripts)
    assert any("Ignoring reconnect from mason" in t for t in actions2.thoughts)

    # After cooldown expires: re-page again.
    actions3 = process_server_text("Mason pages, 'Token: Mason reconnected.'", state, config, now=500.0)
    assert any("Token: Mason go." in s for s in actions3.scripts)
    assert state.last_reconnect_repage_at == 500.0


def test_orchestrator_on_connect_arms_reconnect_cooldown():
    """The deterministic re-page on ``has connected`` must arm the cooldown so
    a follow-up LLM-emitted ``Token: X reconnected`` doesn't re-page again."""
    state = BrainState(token_dispatched_at=None, token_dispatched_to="mason")
    config = _make_config(user="foreman", token_chain=["mason"])
    process_server_text("Mason has connected.", state, config, now=200.0)
    assert state.last_reconnect_repage_at == 200.0
    # Worker's LLM panic-pings 5s later — must be ignored.
    actions = process_server_text("Mason pages, 'Token: Mason reconnected.'", state, config, now=205.0)
    assert not any("page mason with Token:" in s for s in actions.scripts)


def test_dispatch_restored_arms_reconnect_cooldown():
    """The restore-on-Connect re-page (from dispatch.json) must also arm the
    cooldown so a worker's deterministic reconnect ping doesn't trigger a
    second re-page seconds later."""
    state = BrainState(token_dispatched_to="mason")
    config = _make_config(user="foreman", token_chain=["mason"])
    process_server_text("Connected", state, config, now=100.0)
    assert state.last_reconnect_repage_at == 100.0
    actions = process_server_text("Mason pages, 'Token: Mason reconnected.'", state, config, now=105.0)
    assert not any("page mason with Token:" in s for s in actions.scripts)


# --- Worker receives token: deterministic goal injection ---


def test_worker_receives_own_token_clears_goal_and_dispatches_survey():
    """A worker receiving ``Token: <Me> go.`` must have its stale goal
    cleared, ``memory_summary`` set to an unambiguous work directive, and a
    deterministic ``@survey here`` command dispatched so the next LLM cycle
    reacts to concrete world state instead of having to decide whether the
    token is "really" theirs."""
    state = BrainState(current_goal="wait for the token")
    config = _make_config(user="mason", token_chain=[])
    actions = process_server_text("Foreman pages, 'Token: Mason go.'", state, config)
    assert state.current_goal == ""
    assert "received the token" in state.memory_summary.lower()
    assert "begin your assigned work" in state.memory_summary.lower()
    assert "@survey here" in actions.scripts
    assert any("Token received by mason" in t and "@survey here" in t for t in actions.thoughts)


def test_worker_receives_own_token_start_form_also_triggers_injection():
    """The first dispatch uses ``Token: Foreman start.``; treat it the same as
    ``go.`` — both mean ``begin work``."""
    state = BrainState()
    config = _make_config(user="mason", token_chain=[])
    process_server_text("Foreman pages, 'Token: Mason start.'", state, config)
    assert "received the token" in state.memory_summary.lower()


def test_worker_receives_stall_resume_form_also_triggers_injection():
    """Foreman's stall re-page uses ``Token: <Name> resume.`` — treat it the
    same as ``go.`` so a stuck worker gets a fresh work directive on stall
    recovery instead of a noise-shaped page that the LLM ignores."""
    state = BrainState(current_goal="some stale goal")
    config = _make_config(user="mason", token_chain=[])
    process_server_text("Foreman pages, 'Token: Mason resume.'", state, config)
    assert state.current_goal == ""
    assert "received the token" in state.memory_summary.lower()


def test_worker_with_site_suffix_recognizes_token_with_bare_name():
    """The page text uses the bare agent name (``Token: Joiner go.``) even
    when the SSH user includes a +site routing suffix — the worker must
    still match its own token via the bare name."""
    state = BrainState()
    config = _make_config(user="joiner+bijaz.local", token_chain=[])
    actions = process_server_text("Foreman pages, 'Token: Joiner go.'", state, config)
    assert "received the token" in state.memory_summary.lower()
    assert any("Token received by joiner" in t for t in actions.thoughts)


def test_worker_ignores_token_for_other_agent():
    """A worker hearing a Token: page addressed to someone else (broadcast
    leakage from same-room pages) must not clear its own goal."""
    state = BrainState(current_goal="building shelves")
    config = _make_config(user="mason", token_chain=[])
    process_server_text("Foreman pages, 'Token: Tinker go.'", state, config)
    assert state.current_goal == "building shelves"
    assert "received the token" not in state.memory_summary.lower()


def test_orchestrator_does_not_inject_worker_directive():
    """Foreman receiving its own dispatched Token: page (echo or reconnect
    self-page) must not get the worker-side directive — it's not a worker."""
    state = BrainState()
    config = _make_config(user="foreman", token_chain=["mason"])
    process_server_text("Mason pages, 'Token: Foreman start.'", state, config)
    assert "received the token" not in state.memory_summary.lower()


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
