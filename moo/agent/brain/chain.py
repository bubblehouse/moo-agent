"""
Token chain text processing: pure function over server output.

``process_server_text`` is the single entry point. Given a line of raw server
output, the current ``BrainState``, and the agent ``Config``, it classifies
the line, mutates session state in place, and returns a ``ChainActions``
value describing the script-queue pushes, thoughts, and side effects the
``Brain`` should apply.

This keeps ``Brain.run()`` focused on the event loop while making every
chain-relay, reconnect, mail-injection, and dig-advance branch directly
testable against captured fixtures. See ``tests/test_brain_chain.py`` for
the table-driven regression net.
"""

import re
import time
from dataclasses import dataclass, field

from moo.agent.brain.state import BrainState
from moo.agent.config import Config


_DIG_SUCCESS_RE = re.compile(r'^Dug an exit \w+ to "([^"]+)"')
_DIG_ROOM_ID_RE = re.compile(r"Dug \w+ to [^(]+\(#(\d+)\)")
_TOKEN_DONE_RE = re.compile(r"Token:\s+(\w+)\s+done", re.IGNORECASE)
_TOKEN_RECONNECT_RE = re.compile(r"Token:\s+(\w+)\s+reconnected", re.IGNORECASE)
_REPORT_RE = re.compile(r"^\[Mail\] From ([^:]+): (.*)$")
# Match either "pages," (he/she/it) or "page," (they/them) — the page verb
# conjugates based on the sender's pronoun, so both forms appear in server output.
_PAGE_VERB_RE = re.compile(r"\bpages?,")


def _is_page(text: str) -> bool:
    """Return True if the line contains a page verb in either conjugation."""
    return bool(_PAGE_VERB_RE.search(text))


@dataclass
class ChainActions:
    """Side effects the Brain should apply after chain processing."""

    scripts: list[str] = field(default_factory=list)
    """Commands to append to the end of the script queue."""

    scripts_prepend: list[str] = field(default_factory=list)
    """Commands to insert at the front of the script queue (e.g. check_inbox)."""

    thoughts: list[str] = field(default_factory=list)
    """Diagnostic lines to pass to the brain's on_thought callback."""

    save_traversal_plan: bool = False
    """True when session state was reset and the traversal plan should be rewritten."""

    skip: bool = False
    """True for [Mail] lines — Brain should ``continue`` the run loop after applying."""


def process_server_text(
    text: str,
    state: BrainState,
    config: Config,
    now: float | None = None,
) -> ChainActions:
    """
    Classify a server output line and produce the resulting ChainActions.

    All state mutations happen in place on ``state``. The returned
    ``ChainActions`` carries the script-queue pushes, thoughts, and the
    ``skip`` / ``save_traversal_plan`` flags Brain needs to finish applying.
    """
    if now is None:
        now = time.monotonic()

    actions = ChainActions()

    chain = config.agent.token_chain
    my_name = (config.ssh.user or "").lower()
    chain_lower = [a.lower() for a in chain]
    is_orchestrator = bool(chain) and my_name not in chain_lower

    # Orchestrator auto-start: on fresh connection, page the first agent in
    # the token chain without waiting for the LLM to read an operator message.
    # Only fires when this agent IS the orchestrator (not in the chain) and
    # no token has been dispatched yet this session.
    if text == "Connected":
        if chain and is_orchestrator and state.token_dispatched_at is None:
            first = chain[0]
            actions.scripts.append(f"page {first} with Token: Foreman start.")
            actions.scripts.append(f'@describe "agent of the moment" as "The plaque reads: {first.capitalize()}"')
            state.token_dispatched_at = now
            state.token_dispatched_to = first
            actions.thoughts.append(f"[Chain] Auto-starting token chain → {first}")

        # Page-triggered worker reconnect: if this agent had an active goal last
        # session, auto-page the orchestrator so the token is re-sent without
        # waiting for the stall timer or an LLM cycle. Only workers (not
        # orchestrators) do this — orchestrators never wait for a token.
        if state.prior_goal_for_reconnect and not is_orchestrator:
            my_title = (config.ssh.user or "agent").capitalize()
            actions.scripts.append(f"page foreman with Token: {my_title} reconnected.")
            state.prior_goal_for_reconnect = ""  # only fires once per session
            actions.thoughts.append("[Chain] Auto-reconnect page → foreman")

    # Parse REPORT: lines emitted by the check_inbox verb.
    # When the agent runs check_inbox, the server returns a [Mail] line.
    # Suppress [Mail] lines from the rolling window entirely; if a message
    # is present, inject it as memory_summary so the LLM sees prior context.
    if text.startswith("[Mail]"):
        report_match = _REPORT_RE.match(text)
        if report_match:
            sender = report_match.group(1).strip()
            body = report_match.group(2).strip()
            if sender and body:
                state.memory_summary = f"Prior session report from {sender}: {body}"
                actions.thoughts.append(f"[Mail] Injected context from {sender}.")
        actions.skip = True
        return actions

    # Orchestrator: if the target agent was offline when we paged, re-page
    # as soon as they connect.
    if "not currently logged in" in text and state.token_dispatched_to:
        state.token_dispatched_at = None  # allow re-page on connect

    if "has connected" in text and state.token_dispatched_to and state.token_dispatched_at is None:
        target_name = state.token_dispatched_to.lower()
        if target_name in text.lower():
            actions.scripts.append(f"page {state.token_dispatched_to} with Token: Foreman start.")
            actions.scripts.append(
                f'@describe "agent of the moment" as "The plaque reads: {state.token_dispatched_to.capitalize()}"'
            )
            state.token_dispatched_at = now
            actions.thoughts.append(f"[Chain] Re-paging {state.token_dispatched_to} after connect")

    # Track room IDs built this session (Mason expansion pass).
    dig_id_match = _DIG_ROOM_ID_RE.search(text)
    if dig_id_match:
        room_id = f"#{dig_id_match.group(1)}"
        state.rooms_built.append(room_id)
        actions.thoughts.append(f"[Rooms Built] Tracked {room_id} — {len(state.rooms_built)} total this session.")

    # When an incoming token page carries a room list, extract it and
    # set current_plan so the agent visits only those rooms.
    # Also reset session-done state so the LLM can respond.
    if _is_page(text) and "Token:" in text:
        # Reset session state FIRST so the room list extracted below is not
        # immediately overwritten. Workers receive a fresh Rooms: list;
        # Mason starts with an empty plan so it can emit BUILD_PLAN:.
        if state.session_done:
            state.session_done = False
            state.plan_exhausted = False
            state.rooms_built = []
            state.foreman_paged = False
            state.current_plan = []
            actions.save_traversal_plan = True
            actions.thoughts.append("[Token] Reset session state for new pass.")
        # Clear the stall timer when the tracked agent returns done.
        if "done" in text.lower() and state.token_dispatched_at is not None:
            state.token_dispatched_at = None
            actions.thoughts.append("[Stall] Done page received — stall timer cleared.")

        # Auto-relay: if this agent has a token_chain configured AND is not
        # itself a member of that chain (i.e. it is the orchestrator, not a
        # worker), relay done pages to the next agent deterministically.
        # Workers that inherit MOO_TOKEN_CHAIN from the environment must not
        # relay — doing so creates an infinite self-page loop.
        if is_orchestrator and "done" in text.lower():
            done_match = _TOKEN_DONE_RE.search(text)
            if done_match:
                sender = done_match.group(1).lower()
                try:
                    idx = chain_lower.index(sender)
                    next_agent = chain[idx + 1] if idx + 1 < len(chain) else chain[0]
                    msg = f"Token: {done_match.group(1).capitalize()} done."
                    actions.scripts.append(f"page {next_agent} with {msg}")
                    actions.scripts.append(
                        f'@describe "agent of the moment" as "The plaque reads: {next_agent.capitalize()}"'
                    )
                    state.token_dispatched_at = now
                    state.token_dispatched_to = next_agent
                    actions.thoughts.append(f"[Chain] Auto-relaying token from {sender} → {next_agent}")
                except (ValueError, IndexError):
                    pass  # sender not in chain, or no next agent — let LLM handle it

        # Auto-reconnect: if a chain member pages "Token: X reconnected", re-page
        # that same agent — but only if Foreman is currently waiting for it
        # (token_dispatched_to matches) or has no active dispatch. This prevents
        # a batch startup where every worker has a stale goal from flooding Foreman
        # with reconnect pages that each get a token handed back simultaneously.
        if is_orchestrator and "reconnected" in text.lower() and _is_page(text):
            reconnect_match = _TOKEN_RECONNECT_RE.search(text)
            if reconnect_match:
                agent_name = reconnect_match.group(1).lower()
                waiting_for_this = state.token_dispatched_to is None or state.token_dispatched_to.lower() == agent_name
                if agent_name in chain_lower and waiting_for_this:
                    msg = f"Token: {reconnect_match.group(1).capitalize()} go."
                    actions.scripts.append(f"page {agent_name} with {msg}")
                    actions.scripts.append(
                        f'@describe "agent of the moment" as "The plaque reads: {agent_name.capitalize()}"'
                    )
                    state.token_dispatched_at = now
                    state.token_dispatched_to = agent_name
                    actions.thoughts.append(f"[Chain] Auto-reconnect: re-paging {agent_name}")

    # Auto-advance plan: when a @dig succeeds, remove the dug room and all
    # preceding rooms from current_plan (they were already built).
    dig_match = _DIG_SUCCESS_RE.match(text)
    if dig_match and state.current_plan:
        dug_name = dig_match.group(1).strip()
        lower_names = [r.lower() for r in state.current_plan]
        try:
            idx = lower_names.index(dug_name.lower())
            state.current_plan = state.current_plan[idx + 1 :]
            actions.thoughts.append(f"[Plan] Advanced past {dug_name!r} — {len(state.current_plan)} rooms remaining.")
            if not state.current_plan:
                state.plan_exhausted = True
                state.memory_summary = (
                    "BUILD_PLAN fully executed — all rooms are built. "
                    "Do not dig any more rooms. "
                    "Follow your Token Protocol: page your successor, then call done()."
                )
                actions.thoughts.append(
                    "[Plan] All planned rooms built. Follow Token Protocol: page successor, then call done()."
                )
        except ValueError:
            pass  # dug room not in plan (improvised room) — ignore

    return actions
