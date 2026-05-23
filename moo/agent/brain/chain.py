"""
Token chain text processing — pure function over server output. See
``docs/source/explanation/agent-internals.md`` (Token Chain Mechanics) for
the full design narrative. ``tests/test_brain_chain.py`` is the
table-driven regression net.
"""

import re
import time
from dataclasses import dataclass, field
from functools import lru_cache

from moo.agent.brain.state import BrainState
from moo.agent.config import Config


_DIG_SUCCESS_RE = re.compile(r'^Dug an exit \w+ to "([^"]+)"')
_DIG_ROOM_ID_RE = re.compile(r"Dug \w+ to [^(]+\(#(\d+)\)")
_TOKEN_DONE_RE = re.compile(r"Token:\s+(\w+)\s+done", re.IGNORECASE)
# Tolerates an optional `+<site>` suffix on the agent name (multi-universe
# routing), e.g. "Token: Stocker+bijaz.local reconnected."
_TOKEN_RECONNECT_RE = re.compile(r"Token:\s+(\w+)(?:\+\S+)?\s+reconnected", re.IGNORECASE)
# Matches "<Name> has disconnected." — used to clear Foreman's stall timer
# so the next ``has connected`` event triggers an automatic re-page.
_HAS_DISCONNECTED_RE = re.compile(r"^#?\d*\s*\(?([A-Za-z][\w]*)\)?\s+has disconnected\.", re.IGNORECASE)

# Auto-reconnect re-page suppression window. The worker's deterministic
# auto-reconnect page fires once per session on Connect; if the LLM then
# autonomously emits additional ``Token: X reconnected`` pages (panic
# behavior seen on smaller models), Foreman would re-page the worker for
# each one — yielding the 5-pages-in-30s loop we want to break.
_RECONNECT_REPAGE_COOLDOWN_SECONDS = 30.0

# Auto-plan extraction from divine() output. See agent-internals:
# Auto-extracted plans.
_DIVINE_HEADER_RE = re.compile(r"Impressions surface from the noise of the world", re.IGNORECASE)
_ROOM_LISTING_ID_RE = re.compile(r"\(#(\d+)\)")
_REPORT_RE = re.compile(r"^\[Mail\] From ([^:]+): (.*)$")
# "pages," / "page," — the verb conjugates by pronoun; both forms appear.
_PAGE_VERB_RE = re.compile(r"\bpages?,")


def _is_page(text: str) -> bool:
    """Return True if the line contains a page verb in either conjugation."""
    return bool(_PAGE_VERB_RE.search(text))


@lru_cache(maxsize=8)
def _my_token_re(bare_name: str) -> re.Pattern[str]:
    """Per-agent compiled regex matching ``Token: <bare_name> (go|start|resume)``.

    Cached because one agent processes the same ``bare_name`` for the life of
    the process; the prior inline ``re.compile`` ran per incoming token page.
    The 8-entry cap absorbs multi-universe ``+<site>`` variations without
    growing unbounded.
    """
    return re.compile(
        rf"Token:\s+{re.escape(bare_name)}\b[^.]*\b(?:go|start|resume)\b",
        re.IGNORECASE,
    )


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

    save_dispatch_state: bool = False
    """True when Foreman's token_dispatched_to changed — Brain should persist it."""

    clear_dispatch_state: bool = False
    """True when the chain has fully completed (done received from last agent)."""

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

    # On Connected: orchestrator auto-start, worker auto-reconnect page.
    # See agent-internals: Auto-start on connect / Auto-reconnect.
    # Every dispatch message uses the **recipient's** name (``Token: Mason
    # go.``), never the sender's. The worker-side ``my_token_re`` matches on
    # the recipient name to inject the work directive; the older "Token:
    # Foreman start." form silently failed that match.
    if text == "Connected":
        if chain and is_orchestrator and state.token_dispatched_to is None:
            first = chain[0]
            actions.scripts.append(f"page {first} with Token: {first.capitalize()} go.")
            state.token_dispatched_at = now
            state.token_dispatched_to = first
            actions.save_dispatch_state = True
            actions.thoughts.append(f"[Chain] Auto-starting token chain → {first}")
        elif chain and is_orchestrator and state.token_dispatched_to:
            # Restored from dispatch.json — re-page the holder so the worker
            # (often restarted with us) gets a fresh ``Token: X go.`` signal.
            # Without this they sit idle waiting for a page we already know
            # we owe them. The reconnect-handler also re-pages on incoming
            # reconnected-pages, but those arrived to mail while we were down.
            holder = state.token_dispatched_to
            msg = f"Token: {holder.capitalize()} go."
            actions.scripts.append(f"page {holder} with {msg}")
            state.token_dispatched_at = now
            state.last_reconnect_repage_at = now
            actions.save_dispatch_state = True
            actions.thoughts.append(f"[Chain] Resuming — re-paging {holder} with token.")

        if state.prior_goal_for_reconnect and not is_orchestrator:
            raw_user = config.ssh.user or "agent"
            # Strip the +<site> routing suffix used for multi-universe SSH
            # logins; foreman's chain table keys by bare agent name.
            my_title = raw_user.split("+", 1)[0].capitalize()
            actions.scripts.append(f"page foreman with Token: {my_title} reconnected.")
            state.prior_goal_for_reconnect = ""
            actions.thoughts.append("[Chain] Auto-reconnect page → foreman")

    # Suppress [Mail] lines and inject the body as memory_summary.
    # See agent-internals: Mailbox suppression.
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

    # Worker disconnect — clear the stall timer so the next ``has connected``
    # triggers an automatic re-page. Without this, a fast disconnect/reconnect
    # leaves ``token_dispatched_at`` live from the prior heartbeat and the
    # connect handler short-circuits — the worker reconnects but never
    # receives the token again unless Foreman's stall timer fires.
    if is_orchestrator and state.token_dispatched_to and "has disconnected" in text:
        dc_match = _HAS_DISCONNECTED_RE.search(text)
        if dc_match and dc_match.group(1).lower() == state.token_dispatched_to.lower():
            state.token_dispatched_at = None
            state.last_reconnect_repage_at = None  # fresh session
            actions.thoughts.append(
                f"[Chain] {state.token_dispatched_to} disconnected — armed for re-page on reconnect."
            )

    if "has connected" in text and state.token_dispatched_to and state.token_dispatched_at is None:
        target_name = state.token_dispatched_to.lower()
        if target_name in text.lower():
            holder = state.token_dispatched_to
            actions.scripts.append(f"page {holder} with Token: {holder.capitalize()} go.")
            state.token_dispatched_at = now
            state.last_reconnect_repage_at = now
            actions.save_dispatch_state = True
            actions.thoughts.append(f"[Chain] Re-paging {holder} after connect")

    # Track room IDs built this session (Mason expansion pass).
    dig_id_match = _DIG_ROOM_ID_RE.search(text)
    if dig_id_match:
        room_id = f"#{dig_id_match.group(1)}"
        state.rooms_built.append(room_id)
        actions.thoughts.append(f"[Rooms Built] Tracked {room_id} — {len(state.rooms_built)} total this session.")

    # See agent-internals: Auto-extracted plans.
    if _DIVINE_HEADER_RE.search(text):
        room_ids = [f"#{m}" for m in _ROOM_LISTING_ID_RE.findall(text)]
        if room_ids and (not state.current_plan or state.plan_from_disk):
            state.current_plan = room_ids
            state.plan_from_disk = False
            state.plan_exhausted = False
            actions.save_traversal_plan = True
            actions.thoughts.append(
                f"[Auto-Plan] Extracted {len(room_ids)} rooms from divine output: {' | '.join(room_ids)}"
            )

    # Incoming token page: reset session state so the new pass starts clean.
    if _is_page(text) and "Token:" in text:
        if state.session_done:
            state.session_done = False
            state.plan_exhausted = False
            state.rooms_built = []
            state.foreman_paged = False
            state.current_plan = []
            actions.save_traversal_plan = True
            actions.thoughts.append("[Token] Reset session state for new pass.")

        # Worker receiving its own ``Token: <Me> go.`` (or ``start.``) — strip
        # the +<site> routing suffix for a bare-name match against the page,
        # then pre-load ``current_goal`` with an unambiguous directive so the
        # next LLM cycle starts work instead of asking whether the token is
        # really theirs. Without this, smaller models often answer the page
        # with a panic ping ("Token: X ready/waiting/ping") and burn the pass
        # before any work happens.
        if not is_orchestrator and my_name:
            bare_name = my_name.split("+", 1)[0]
            # ``go`` / ``start`` are the first-dispatch and chain-relay forms;
            # ``resume`` is the Foreman stall-page form. All three are "you
            # have the token, begin or continue work" signals.
            if _my_token_re(bare_name).search(text):
                state.current_goal = ""
                state.memory_summary = (
                    "You have just received the token. Begin your assigned work "
                    "immediately as described in your SOUL. The deterministic "
                    "chain has routed this page to you — there is no further "
                    "check needed."
                )
                # Deterministic first action: dispatch ``@survey here`` so the
                # LLM's first cycle reacts to concrete world state (room ID,
                # exits, contents with IDs, residents) instead of having to
                # decide whether the token is "really" theirs. The LLM
                # routinely answers a fresh page with a ``respond()`` saying
                # "I'm waiting for the token"; landing actual structured room
                # state in the window breaks that pattern by giving the model
                # something specific to act on.
                actions.scripts.append("@survey here")
                actions.thoughts.append(
                    f"[Chain] Token received by {bare_name} — cleared stale goal, "
                    "dispatched '@survey here' to seed world state for the LLM cycle."
                )
        # Clear the stall timer on ANY ``Token:`` page from the holder — done
        # means the pass is finished, working/reconnected mean the holder is
        # alive and Foreman can defer the next stall page. Without the
        # heartbeat reset, a slow-but-progressing worker gets stall-paged
        # every 180s and tends to surrender the token without building.
        is_orchestrator_recv = is_orchestrator and state.token_dispatched_to is not None
        if is_orchestrator_recv and state.token_dispatched_at is not None:
            holder_lower = state.token_dispatched_to.lower()
            if holder_lower in text.lower():
                state.token_dispatched_at = None
                label = "Done" if "done" in text.lower() else "Heartbeat"
                actions.thoughts.append(f"[Stall] {label} page from {holder_lower} — stall timer cleared.")

        # See agent-internals: Auto-relay. Workers must not relay or they
        # self-loop on their own done pages.
        if is_orchestrator and "done" in text.lower():
            done_match = _TOKEN_DONE_RE.search(text)
            if done_match:
                sender = done_match.group(1).lower()
                try:
                    idx = chain_lower.index(sender)
                    next_agent = chain[idx + 1] if idx + 1 < len(chain) else chain[0]
                    msg = f"Token: {next_agent.capitalize()} go."
                    actions.scripts.append(f"page {next_agent} with {msg}")
                    state.token_dispatched_at = now
                    state.token_dispatched_to = next_agent
                    actions.save_dispatch_state = True
                    actions.thoughts.append(f"[Chain] Auto-relaying token from {sender} → {next_agent}")
                except (ValueError, IndexError):
                    pass

        # See agent-internals: Auto-reconnect.
        if is_orchestrator and "reconnected" in text.lower() and _is_page(text):
            reconnect_match = _TOKEN_RECONNECT_RE.search(text)
            if reconnect_match:
                agent_name = reconnect_match.group(1).lower()
                waiting_for_this = state.token_dispatched_to is None or state.token_dispatched_to.lower() == agent_name
                # Cooldown: if we re-paged this agent recently (their
                # deterministic auto-reconnect page is usually the trigger),
                # ignore any additional ``Token: X reconnected`` pages so a
                # chatty LLM cannot spam Foreman into a re-page loop.
                recently_repaged = (
                    state.last_reconnect_repage_at is not None
                    and (now - state.last_reconnect_repage_at) < _RECONNECT_REPAGE_COOLDOWN_SECONDS
                )
                if agent_name in chain_lower and waiting_for_this and not recently_repaged:
                    msg = f"Token: {reconnect_match.group(1).capitalize()} go."
                    actions.scripts.append(f"page {agent_name} with {msg}")
                    state.token_dispatched_at = now
                    state.token_dispatched_to = agent_name
                    state.last_reconnect_repage_at = now
                    actions.save_dispatch_state = True
                    actions.thoughts.append(f"[Chain] Auto-reconnect: re-paging {agent_name}")
                elif agent_name in chain_lower and recently_repaged:
                    actions.thoughts.append(
                        f"[Chain] Ignoring reconnect from {agent_name} — already re-paged in last "
                        f"{int(_RECONNECT_REPAGE_COOLDOWN_SECONDS)}s."
                    )

    # Auto-advance the plan when a @dig succeeds.
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
            pass  # improvised room not in plan — ignore

    return actions
