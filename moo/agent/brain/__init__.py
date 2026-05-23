"""
Brain: perception-action loop for moo-agent.

See ``docs/source/explanation/agent-internals.md`` for the full design
narrative — the Perception-Action Loop, Script Queue, and One LLM Cycle
sections cover everything in this module.
"""

import asyncio
import collections
import enum
import os
import re
import time
from pathlib import Path
from typing import Callable

import logfire
from asynciolimiter import LeakyBucketLimiter
from pydantic_ai.exceptions import ModelHTTPError, UnexpectedModelBehavior, UsageLimitExceeded

from moo.agent.brain.chain import process_server_text, _is_page
from moo.agent.brain.deps import BrainDeps
from moo.agent.brain.prompt import (
    build_system_prompt,
    build_user_message,
)
from moo.agent.brain.plans import (
    clear_dispatch_state,
    load_dispatch_state,
    load_latest_build_plan,
    load_traversal_plan,
    save_build_plan,
    save_dispatch_state,
    save_traversal_plan,
)
from moo.agent.brain.state import BrainState
from moo.agent.connection import MooConnection
from moo.agent.llm_client import call_llm, make_agent
from moo.agent.response_model import AgentResponse
from moo.agent.soul import Soul, append_patch_directive, compile_rules, parse_soul


class Status(enum.Enum):
    READY = "ready"
    WAITING = "waiting"
    SLEEPING = "sleeping"
    THINKING = "thinking"


# Matches "look <verb> #N" — the canonical wrong way to test a verb. The
# parser treats the whole tail as a single object name lookup, which fails.
_LOOK_VERB_TEST_RE = re.compile(r"^look\s+([a-z@][\w-]*)\s+(#\d+)$", re.IGNORECASE)
# Matches "There is no '<verb> #N' here" — the error produced by the parser
# when given a malformed verb test.
_NO_SUCH_VERB_TEST_RE = re.compile(r"^There is no '([a-z@][\w-]*\s+#\d+)' here", re.IGNORECASE)
# Matches a short unit (2-20 chars) repeated 7+ times in a row — the signature
# of Gemma token-loop degeneration (e.g. "_plan_plan_plan…", "related-related…").
# A summary that matches must be discarded before it poisons later prompts.
_DEGENERATE_RE = re.compile(r"(.{2,20}?)\1{6,}")


_ERROR_PREFIXES = (
    "Error:",
    "Traceback",
    "Exception:",
    "TypeError:",
    "ValueError:",
    "AttributeError:",
    "KeyError:",
    "IndexError:",
    "PermissionError:",
    "There is no ",
    "I don't understand",
    "You can't",
    "That doesn't",
    "Huh?",
    "There is already an exit",
    "An error occurred",
    "<|",
    "Go where?",
    "Usage:",
    "When you say,",
    "More than one object defines",
    "That alias",
)


# Substrings that mark an otherwise error-shaped line as benign. "is already
# set" is the idempotent alias response — the alias IS set, so aborting the
# script and handing back to the LLM just burns cycles on a no-op.
_BENIGN_SUBSTRINGS = ("is already set",)


def looks_like_error(text: str) -> bool:
    first_line = text.lstrip().split("\n")[0]
    if any(s in first_line for s in _BENIGN_SUBSTRINGS):
        return False
    return any(first_line.startswith(p) for p in _ERROR_PREFIXES)


class Brain:
    """
    Async perception-action loop. See the agent-internals doc for design
    details (Perception-Action Loop, Wakeup Modes, Stall Detection).
    """

    def __init__(
        self,
        soul: Soul,
        config,
        connection: MooConnection,
        on_thought: Callable[[str], None],
        config_dir: Path | None = None,
        on_status_change: Callable[[Status], None] | None = None,
        prior_session_summary: str = "",
        prior_goal: str = "",
        on_action_sent: Callable[[str], None] | None = None,
        tools: list[str] | None = None,
    ):
        self._soul = soul
        self._config = config
        self._connection = connection
        self._on_thought = on_thought
        self._config_dir = config_dir
        self._on_status_change = on_status_change
        self._on_action_sent = on_action_sent
        self._tool_names = tools

        self._output_queue: asyncio.Queue[str] = asyncio.Queue()
        self._window: collections.deque[str] = collections.deque(maxlen=config.agent.memory_window_lines)
        self._compiled_rules = compile_rules(soul)
        self._limiter = LeakyBucketLimiter(config.agent.command_rate_per_second)
        self._llm_sem = asyncio.Semaphore(1)
        self._status = Status.WAITING if config.agent.idle_wakeup_seconds == 0 else Status.READY
        self._last_activity = time.monotonic()
        self._recent_cmds: collections.deque[str] = collections.deque(maxlen=8)

        # Page-triggered agents start cold and use prior_goal only for the
        # auto-reconnect page. See agent-internals: Wakeup Modes / Session Resume.
        page_triggered = self._config.agent.idle_wakeup_seconds == 0
        self._state = BrainState(
            current_goal="" if page_triggered else prior_goal,
            prior_goal_for_reconnect=prior_goal if page_triggered else "",
            memory_summary=prior_session_summary,
        )

        self._load_latest_build_plan()
        if not self._state.current_plan and not page_triggered:
            self._load_traversal_plan()

        # The system prompt is static for the session — soul is fixed — so it
        # is built once and held on the Agent. Tools are registered on the
        # Agent itself via ``make_agent``; the prompt no longer renders them.
        system_prompt = build_system_prompt(soul)
        # Single Agent keeps LM Studio's KV cache warm across cycles.
        # PydanticAI Agent name is the fixed project label so all agents roll
        # up in the Logfire Agents view; per-process identity rides on
        # service_name (set in cli.run_agent) and the ``agent`` span attribute.
        self._agent = make_agent(
            config.llm,
            system_prompt,
            retries=config.agent.instructor_retries,
            name="moo-agent",
            tool_names=self._tool_names,
        )

        chain_lower = [a.lower() for a in config.agent.token_chain]
        self._is_orchestrator = bool(chain_lower) and (config.ssh.user or "").lower() not in chain_lower

        # Foreman: restore who held the token across restarts. Without this, a
        # mid-chain restart wipes state.token_dispatched_to, and the Connected
        # handler auto-pages the first chain agent — disrupting whoever was
        # mid-pass. See plans.save_dispatch_state for the why.
        if self._is_orchestrator:
            load_dispatch_state(self._config_dir, self._state, self._on_thought)

    def _set_status(self, status: Status) -> None:
        # Page-triggered agents show "waiting" while idle.
        if status == Status.READY and self._config.agent.idle_wakeup_seconds == 0:
            status = Status.WAITING
        if status != self._status:
            self._status = status
            if self._on_status_change is not None:
                self._on_status_change(status)

    def enqueue_output(self, text: str) -> None:
        """Called by the connection layer when server output arrives."""
        self._last_activity = time.monotonic()
        self._output_queue.put_nowait(text)

    def process_tool_response(self, text: str) -> None:
        """
        Side-channel handler for bracketed slices that ``MooConnection.request()``
        consumes. The model already saw the slice (as the tool's return value),
        so we do NOT push it onto ``_output_queue`` — that would double-expose
        in the rolling window. We still run room-tracking against it so
        ``current_room_id``/``current_room_name`` stay fresh after every
        ``go``/``burrow``/``teleport``; everything else (token chain, auto-advance)
        flows through unsolicited text on the regular ``on_output`` path.
        """
        if not text:
            return
        self._last_activity = time.monotonic()
        self._update_current_room_from(text)

    def enqueue_instruction(self, text: str) -> None:
        """Operator instruction from the TUI — bypass rules, force an LLM cycle."""
        self._last_activity = time.monotonic()
        self._window.append(f"[Operator]: {text}")
        asyncio.get_event_loop().create_task(self._llm_cycle())

    def _build_user_message(self) -> str:
        """Thin wrapper around ``brain_prompt.build_user_message``."""
        return build_user_message(
            memory_summary=self._state.memory_summary,
            current_goal=self._state.current_goal,
            current_plan=self._state.current_plan,
            plan_exhausted=self._state.plan_exhausted,
            idle_wakeup_count=self._state.idle_wakeup_count,
            window_lines=self._window,
        )

    async def run(self) -> None:
        """
        Main perception-action loop. See agent-internals: Perception-Action
        Loop.

        Stage-2: command dispatch happens inside the PydanticAI tool loop
        (each ``@agent.tool`` calls ``MooConnection.request()`` directly), so
        this loop only ingests server output, applies chain.py side effects,
        and decides when to fire an LLM cycle.
        """
        if self._config.agent.idle_wakeup_seconds > 0:
            asyncio.create_task(self._wakeup_loop())
        if self._config.agent.stall_timeout_seconds > 0:
            asyncio.create_task(self._stall_check_loop())
        pending_llm = False
        while True:
            try:
                text = await asyncio.wait_for(self._output_queue.get(), timeout=0.3)
            except asyncio.TimeoutError:
                if pending_llm:
                    pending_llm = False
                    if not self._state.session_done:
                        asyncio.create_task(self._llm_cycle())
                    else:
                        # session_done blocks the cycle but status must reset
                        # so the wakeup loop can still fire.
                        self._set_status(Status.READY)
                continue

            self._set_status(Status.THINKING)
            self._window.append(text)
            self._state.idle_wakeup_count = 0
            self._state.goal_only_count = 0

            self._check_verb_test_mistake(text)
            self._update_current_room_from(text)

            actions = process_server_text(text, self._state, self._config, time.monotonic())
            for cmd in actions.scripts_prepend:
                await self._dispatch(cmd)
            for cmd in actions.scripts:
                await self._dispatch(cmd)
            for thought in actions.thoughts:
                self._on_thought(thought)
            if actions.save_traversal_plan:
                self._save_traversal_plan()
            if actions.save_dispatch_state:
                save_dispatch_state(self._config_dir, self._state, self._on_thought)
            if actions.clear_dispatch_state:
                clear_dispatch_state(self._config_dir)
            if actions.skip:
                continue

            window_max = self._window.maxlen or 50
            if len(self._window) >= window_max - 10:
                self._trim_window()

            matched = self._check_rules(text)
            if matched:
                await self._dispatch(matched)
                pending_llm = False
                self._set_status(Status.READY)
            else:
                # Defer the LLM cycle to the next quiet tick so multi-line
                # tell() bursts arrive whole. See agent-internals:
                # Pending-LLM Gating for the suppression conditions.
                if self._config.agent.idle_wakeup_seconds == 0 and not self._state.current_goal and not _is_page(text):
                    self._set_status(Status.READY)
                elif self._is_orchestrator:
                    pass
                elif self._config.agent.timer_only:
                    self._set_status(Status.READY)
                elif not self._state.session_done:
                    pending_llm = True

    async def _wakeup_loop(self) -> None:
        """
        Idle wakeup timer for timer-based agents. See agent-internals:
        Wakeup Modes — Timer-based.
        """
        wakeup_s = self._config.agent.idle_wakeup_seconds
        if wakeup_s == 0:
            return
        warn_threshold = min(10.0, wakeup_s)
        while True:
            await asyncio.sleep(1.0)
            if self._status == Status.THINKING:
                continue
            elapsed = time.monotonic() - self._last_activity
            remaining = wakeup_s - elapsed
            if remaining <= warn_threshold and self._status == Status.READY:
                self._set_status(Status.SLEEPING)
            if remaining <= 0:
                self._last_activity = time.monotonic()
                if not (self._state.plan_exhausted and not self._state.current_goal) and not self._state.session_done:
                    self._state.idle_wakeup_count += 1
                    if self._config.agent.clear_window_on_wakeup:
                        self._window.clear()
                    self._state.current_goal = ""
                    asyncio.create_task(self._llm_cycle())

    async def _stall_check_loop(self) -> None:
        """
        Deterministic stall detector — re-pages the token holder if it hasn't
        responded within ``stall_timeout_seconds``. Bypasses the LLM. See
        agent-internals: Stall Detection.
        """
        stall_s = self._config.agent.stall_timeout_seconds
        if stall_s <= 0:
            return
        while True:
            await asyncio.sleep(30.0)
            if self._state.token_dispatched_at is None or self._state.session_done:
                continue
            elapsed = time.monotonic() - self._state.token_dispatched_at
            if elapsed < stall_s:
                continue
            agent = self._state.token_dispatched_to
            if not agent:
                continue
            if await self._target_is_actively_cycling(agent, stall_s):
                continue
            self._on_thought(f"[Stall] {agent} has not responded in {elapsed:.0f}s — re-paging.")
            # Use the ``Token: <Name> resume.`` form so the worker's chain.py
            # token-receive injector clears any stale goal and reloads the
            # work directive — recovers stuck workers without LLM ambiguity.
            # No internal punctuation: a mid-line ``,`` or ``. `` splits the
            # tail into a separate command that dispatches as "Huh?".
            command = f"page {agent} with Token: {agent.capitalize()} resume."
            await self._dispatch(command)
            self._state.token_dispatched_at = time.monotonic()

    async def _target_is_actively_cycling(self, agent: str, stall_s: int) -> bool:
        """
        Ask ``agentmux cycle-age`` whether the target is still inside a
        plausible cycle (age < max(stall_s, 3×p95)). Returns False on any
        configuration or subprocess failure so the re-page still fires.
        """
        group = os.environ.get("MOO_TOKEN_CHAIN_GROUP")
        agentmux = os.environ.get("MOO_AGENTMUX_PATH")
        if not group or not agentmux:
            return False
        try:
            proc = await asyncio.create_subprocess_exec(
                agentmux,
                "--group",
                group,
                "cycle-age",
                agent,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
            if proc.returncode != 0:
                return False
            parts = stdout.decode().strip().split()
            if len(parts) != 2:
                return False
            age = int(parts[0])
            p95 = float(parts[1])
        except (asyncio.TimeoutError, ValueError, FileNotFoundError, OSError):
            return False
        if age < 0 or p95 < 0:
            return False
        adaptive_threshold = max(stall_s, int(3 * p95))
        if age < adaptive_threshold:
            self._on_thought(
                f"[Stall] {agent} elapsed={age}s within 3×p95={int(3 * p95)}s — still cycling, skipping re-page."
            )
            return True
        return False

    def _check_rules(self, text: str) -> str | None:
        """Return the command for the first matching rule, or None."""
        for pattern, command in self._compiled_rules:
            if pattern.search(text):
                return command
        return None

    def _resolve_intent(self, text: str) -> str:
        """Map an intent name to its MOO command template, or return as-is."""
        lower = text.strip().lower()
        for vm in self._soul.verb_mappings:
            if vm.intent.lower() == lower:
                return vm.template
        return text.strip()

    async def _call_llm(self, user_message: str, max_tokens: int, deps: BrainDeps) -> tuple[AgentResponse, int]:
        """Thin instance-method shim around ``llm_client.call_llm`` — returns (output, tool_calls)."""
        return await call_llm(
            self._agent,
            self._config.llm,
            user_message,
            max_tokens,
            deps=deps,
            tool_calls_limit=self._config.agent.tool_calls_per_cycle,
            temperature=self._config.agent.temperature,
            top_p=self._config.agent.top_p,
            top_k=self._config.agent.top_k,
            repeat_penalty=self._config.agent.repeat_penalty,
            min_p=self._config.agent.min_p,
        )

    def _make_deps(self) -> BrainDeps:
        """Build the per-cycle ``BrainDeps`` payload tools receive via ``RunContext``."""
        return BrainDeps(
            connection=self._connection,
            limiter=self._limiter,
            soul_name=self._soul.name or "agent",
            current_room_id=self._state.current_room_id,
            current_room_name=self._state.current_room_name,
            on_thought=self._on_thought,
            on_window_append=self._record_tool_dispatch,
        )

    def _record_tool_dispatch(self, line: str) -> None:
        """Append a tool's dispatched-command marker line to the window + TUI log."""
        self._window.append(line)
        cmd = line[2:] if line.startswith("> ") else line
        self._check_command_loop(cmd)
        if self._on_action_sent:
            self._on_action_sent(cmd)

    def _trim_window(self) -> None:
        """
        Drop the oldest half of the rolling window — plain truncation.

        This replaces LLM-based summarization. The local model cannot
        summarize free-form text without degenerating into token loops, and
        a degenerate summary stored as ``memory_summary`` poisons every later
        prompt. Dropping the oldest lines outright is deterministic and safe;
        recent context (the half that matters) is untouched.
        """
        window_max = self._window.maxlen or 50
        n = window_max // 2
        if len(self._window) < n:
            return
        remaining = list(self._window)[n:]
        self._window.clear()
        self._window.extend(remaining)

    async def _llm_cycle(self) -> None:
        """
        Single LLM inference cycle, skip-on-busy. See agent-internals:
        One LLM Cycle.
        """
        if self._llm_sem.locked():
            return
        if self._state.pending_done_msg:
            self._on_thought(self._state.pending_done_msg)
            self._state.pending_done_msg = ""
        self._set_status(Status.THINKING)
        cycle_start = time.monotonic()

        async with self._llm_sem:
            # The auto-instrumented LLM call nests under this span via OTEL
            # context, so one trace = goal + LLM call + tokens/cost + outcome.
            with logfire.span("llm_cycle", agent=self._config.ssh.user or "moo-agent") as span:
                await self._run_cycle_body(span, cycle_start)

    async def _run_cycle_body(self, span, cycle_start: float) -> None:
        """
        Body of one LLM cycle. ``span`` records goal, tool count, outcome.

        Stage-2: ``agent.run()`` runs the PydanticAI tool loop internally.
        Each ``@agent.tool`` dispatches its MOO command via
        ``deps.connection.request()`` and returns the bracketed response to
        the model, so by the time ``_call_llm`` returns, every action the
        model wanted to take has already hit the world.
        """
        user_message = self._build_user_message()
        deps = self._make_deps()

        outcome = await self._run_llm_with_retry(user_message, deps)
        if outcome is None:
            span.set_attribute("outcome", "llm_failed")
            self._emit_cycle_stats(cycle_start, tool_calls=0, dispatched=False)
            self._set_status(Status.READY)
            return
        resp, tool_calls_count = outcome

        self._apply_agent_response(resp, deps)
        span.set_attribute("goal", resp.goal or "")
        span.set_attribute("tool_calls", tool_calls_count)
        if resp.done:
            span.set_attribute("done", resp.done)

        if resp.reasoning:
            self._on_thought(resp.reasoning)

        if tool_calls_count == 0:
            # Goal-only re-cycle (capped). See agent-internals:
            # The goal-only re-cycle counter.
            if (
                self._state.current_goal
                and not self._state.session_done
                and not self._state.plan_exhausted
                and not self._is_orchestrator
                and self._state.goal_only_count < 3
            ):
                self._state.goal_only_count += 1
                asyncio.create_task(self._llm_cycle())
            elif self._state.goal_only_count == 3 and not self._state.session_done and not self._is_orchestrator:
                # Final escalation: 3 zero-action cycles in a row. Inject an
                # explicit operator nudge and grant one more cycle so the
                # agent has a chance to recover by paging Foreman + calling
                # done() instead of stalling silently.
                self._state.goal_only_count += 1
                nudge = (
                    "You have produced three responses with no tool calls. "
                    "Stop asking the operator for the next room. If your work "
                    "is complete, page Foreman with 'Token: <Name> done.' and "
                    "then call done(). If you are stuck, page Foreman with a "
                    "short status and call done(). Do not produce another "
                    "commentary-only response."
                )
                self._window.append(f"[Operator]: {nudge}")
                self._on_thought("[Stall] Three empty cycles — injecting recovery nudge.")
                asyncio.create_task(self._llm_cycle())
            span.set_attribute("outcome", "goal_only")
            self._emit_cycle_stats(cycle_start, tool_calls=tool_calls_count, dispatched=False)
            self._set_status(Status.READY)
            return

        # Worker mid-mission auto-recycle. A productive cycle ending without a
        # done signal means the LLM stopped early — it set a goal, fired a few
        # tool calls, but didn't reach the page-done + done() handoff. Tool
        # responses go through ``process_tool_response`` (side-channel) which
        # does NOT trigger ``pending_llm``, so without an explicit re-cycle
        # the worker sits idle until Foreman's stall timer fires.
        if (
            tool_calls_count > 0
            and not self._state.session_done
            and not self._state.foreman_paged
            and not self._is_orchestrator
            and self._state.goal_only_count < 10
        ):
            self._state.goal_only_count += 1
            asyncio.create_task(self._llm_cycle())

        span.set_attribute("outcome", "dispatched")
        self._emit_cycle_stats(cycle_start, tool_calls=tool_calls_count, dispatched=True)
        self._set_status(Status.READY)

    def _emit_cycle_stats(self, cycle_start: float, *, tool_calls: int, dispatched: bool) -> None:
        duration = time.monotonic() - cycle_start
        self._on_thought(
            f"[Cycle] duration={duration:.1f}s tool_calls={tool_calls} "
            f"outcome={'dispatched' if dispatched else 'goal_only'}"
        )

    async def _run_llm_with_retry(self, user_message: str, deps: BrainDeps) -> tuple[AgentResponse, int] | None:
        """
        Call the LLM with 529-overload retries (5 s, 10 s, 20 s backoff).
        Returns ``(output, tool_calls)`` on success, or None on a hard failure
        so ``_llm_cycle`` falls through to the goal-only recovery-nudge path.
        """
        for attempt in range(4):
            try:
                return await self._call_llm(user_message, self._config.agent.max_tokens, deps)
            except ModelHTTPError as exc:
                if exc.status_code == 529 and attempt < 3:
                    delay = 5 * 2**attempt
                    self._on_thought(f"[LLM overloaded] retrying in {delay}s (attempt {attempt + 1}/3)")
                    await asyncio.sleep(delay)
                    continue
                self._on_thought(f"[LLM error] {exc}")
                return None
            except UsageLimitExceeded as exc:
                # The model burned through ``tool_calls_per_cycle`` without
                # paging Foreman + signaling done. For workers, the chain
                # otherwise stalls until Foreman's timer fires and the worker
                # is unlikely to recover gracefully on the re-page. Auto-pass
                # the token: page Foreman done and mark session_done so the
                # chain advances deterministically. Whatever work landed in
                # the first 20 calls stands; if the worker was thrashing,
                # the next worker takes over which is still better than an
                # indefinite stall.
                self._on_thought(f"[Cycle] tool_call_cap_hit — {exc}")
                if not self._is_orchestrator and not self._state.session_done:
                    agent_name = self._soul.name or "Agent"
                    done_msg = f"Token: {agent_name} done. (tool_call_cap_hit)"
                    self._on_thought(f"[Chain] Auto-passing token after cap hit — paging foreman with '{done_msg}'.")
                    asyncio.create_task(self._dispatch(f"page foreman with {done_msg}"))
                    self._state.foreman_paged = True
                    self._state.session_done = True
                return None
            except UnexpectedModelBehavior as exc:
                self._on_thought(f"[LLM] structured-output validation failed after retries — {exc}")
                return None
            except Exception as exc:  # pylint: disable=broad-exception-caught
                self._on_thought(f"[LLM error] {exc}")
                return None
        return None

    def _apply_agent_response(self, resp: AgentResponse, deps: BrainDeps) -> None:
        """
        Apply meta-state from a validated ``AgentResponse`` and fold back the
        side-effect mutations side-effecting tools made through ``deps``.
        """
        if resp.goal and resp.goal != self._state.current_goal:
            self._state.current_goal = resp.goal
            self._on_thought(f"[Goal] {resp.goal}")

        if resp.plan is not None:
            self._state.current_plan = [s.strip() for s in resp.plan if s.strip()]
            self._save_traversal_plan()

        for patch in resp.soul_patches:
            self._apply_patch(patch.kind, patch.content)

        if resp.build_plan:
            self._save_build_plan(resp.build_plan)

        # Fold back side-effect state from tools.
        if deps.token_dispatched_to:
            self._state.token_dispatched_at = deps.token_dispatched_at
            self._state.token_dispatched_to = deps.token_dispatched_to
        if deps.foreman_paged:
            self._state.foreman_paged = True

        # Done signal — either tool-driven (deps.session_done) or field-driven
        # (resp.done). Both funnel through ``_handle_done`` so the foreman-paged
        # guard still applies.
        if deps.session_done:
            self._handle_done(deps.pending_done_msg)
        elif resp.done is not None:
            self._handle_done(resp.done)

    def _handle_done(self, summary: str) -> None:
        """
        Apply a completion signal, gated by the foreman-paged guard. Until
        Foreman has been paged with 'Token: ... done.', a done signal is
        blocked and rewritten into a CRITICAL goal nudge. See agent-internals:
        Done and foreman_paged guard.
        """
        if not self._state.foreman_paged and not self._state.session_done:
            agent_name = self._soul.name or "Agent"
            self._on_thought(
                f"[Done] Blocked — page Foreman first, then signal done. "
                f"Your IMMEDIATE next action: "
                f"page(target='foreman', message='Token: {agent_name} done.')"
            )
            self._state.current_goal = (
                f"CRITICAL: call page(target='foreman', "
                f"message='Token: {agent_name} done.') — this is your only next action"
            )
            return
        summary = (summary or "").strip()
        self._state.pending_done_msg = summary
        self._state.current_goal = ""
        self._state.session_done = True
        if summary:
            self._on_thought(f"[Done] {summary}")

    def _apply_patch(self, entry_type: str, directive: str) -> None:
        """Parse a patch directive and append to SOUL.patch.md, then reload rules."""
        if not self._config_dir:
            return
        if not append_patch_directive(self._config_dir, entry_type, directive):
            return
        try:
            updated = parse_soul(self._config_dir)
            self._soul.rules = updated.rules
            self._soul.verb_mappings = updated.verb_mappings
            self._soul.context = updated.context
            self._compiled_rules = compile_rules(self._soul)
        except Exception:  # pylint: disable=broad-exception-caught
            pass

    def _save_traversal_plan(self) -> None:
        save_traversal_plan(self._config_dir, self._state, self._on_thought)

    def _load_traversal_plan(self) -> None:
        load_traversal_plan(self._config_dir, self._state, self._on_thought)

    def _load_latest_build_plan(self) -> None:
        load_latest_build_plan(self._config_dir, self._state, self._on_thought)

    def _save_build_plan(self, content: str) -> None:
        save_build_plan(self._config_dir, self._state, self._on_thought, content)

    _ROOM_MOVE_RE = re.compile(r"^You move to ([^(\n]+?) \((#\d+)\)\.\s*$")
    # @burrow / @dig emit "You are now in X (#N)." after digging into a new
    # room, instead of the standard "You move to" wording. Without this, a
    # successful dig leaves current_room_* pointing at the source room.
    _ROOM_NOW_IN_RE = re.compile(r"^You are now in ([^(\n]+?) \((#\d+)\)\.\s*$")
    _ROOM_HEADER_RE = re.compile(r"^([^\n]+?) \((#\d+)\)\s*$")

    def _update_current_room_from(self, text: str) -> None:
        """Parse room-announcing server lines and update current_room state."""
        for line in text.splitlines():
            stripped = line.strip()
            m = self._ROOM_MOVE_RE.match(stripped) or self._ROOM_NOW_IN_RE.match(stripped)
            if m:
                self._state.current_room_name = m.group(1).strip()
                self._state.current_room_id = m.group(2)
                return
            m = self._ROOM_HEADER_RE.match(stripped)
            if m and "Exits:" in text:
                self._state.current_room_name = m.group(1).strip()
                self._state.current_room_id = m.group(2)
                return

    # Bare-direction words and the ``go <dir>`` family. Issuing the same
    # direction from a new room is healthy exploration through a corridor
    # or maze, not a stuck loop — repeating direction strings should reset
    # the recent-command window rather than accumulating.
    _MOVEMENT_WORDS = frozenset(
        {
            "n",
            "s",
            "e",
            "w",
            "u",
            "d",
            "ne",
            "nw",
            "se",
            "sw",
            "north",
            "south",
            "east",
            "west",
            "up",
            "down",
            "northeast",
            "northwest",
            "southeast",
            "southwest",
            "in",
            "out",
            "enter",
            "exit",
        }
    )

    _RELOCATE_PREFIXES = ("@burrow", "@dig", "@teleport", "teleport")

    def _is_movement(self, cmd: str) -> bool:
        norm = cmd.strip().lower()
        if norm in self._MOVEMENT_WORDS:
            return True
        if norm.startswith("go "):
            return norm[3:].strip() in self._MOVEMENT_WORDS
        first = norm.split(None, 1)[0] if norm else ""
        return first in self._RELOCATE_PREFIXES

    def _check_verb_test_mistake(self, text: str) -> None:
        """
        Detect the 'look <verb> #N' anti-pattern. When the last command sent
        matches that shape and the server replied 'There is no <verb> #N
        here', inject an operator hint nudging the agent to invoke the verb
        directly. Fires on the first occurrence, not the third — the loop
        detector handles repeats.
        """
        first_line = text.lstrip().split("\n", 1)[0]
        err = _NO_SUCH_VERB_TEST_RE.match(first_line)
        if not err:
            return
        if not self._recent_cmds:
            return
        last_cmd = self._recent_cmds[-1]
        cmd_match = _LOOK_VERB_TEST_RE.match(last_cmd.strip())
        if not cmd_match:
            return
        verb, ref = cmd_match.group(1), cmd_match.group(2)
        hint = (
            f"'look {verb} {ref}' is the wrong shape for testing a verb. "
            f"Send '{verb} {ref}' directly (no 'look' prefix). The parser "
            "treats 'look <verb> #N' as one object name and fails."
        )
        self._window.append(f"[Operator]: {hint}")
        self._on_thought("[Hint] Verb-test mistake detected — injected operator note.")

    def _check_command_loop(self, cmd: str) -> None:
        """
        Inject an operator warning into the rolling window when the same
        non-movement command appears 3+ times in the last 8 sent. Movement
        commands clear the tracker — repeated direction strings during
        exploration should not trigger the warning, since each successful
        move is a different room. Resets the tracker after firing so the
        warning doesn't repeat on every subsequent command.
        """
        if self._is_movement(cmd):
            self._recent_cmds.clear()
            return
        self._recent_cmds.append(cmd)
        count = sum(1 for c in self._recent_cmds if c == cmd)
        if count >= 3:
            self._recent_cmds.clear()
            warning = (
                f"You sent '{cmd}' {count} times in the last few commands — "
                "you are stuck in a loop. Stop. Try a completely different approach."
            )
            self._window.append(f"[Operator]: {warning}")
            self._on_thought(f"[Loop] Detected repetition of '{cmd}' × {count} — injecting operator warning.")

    async def _dispatch(self, command: str) -> None:
        """
        Rate-limited fire-and-forget dispatch for non-tool commands — chain
        auto-advance (e.g. ``check_inbox``), rule-matched responses, and the
        stall re-page. Tool commands dispatch directly via
        ``MooConnection.request()`` from inside ``agent_tools``.
        """
        if not command.strip():
            return
        await self._limiter.wait()
        self._window.append(f"> {command}")
        self._connection.send(command)
        self._check_command_loop(command)
        if self._on_action_sent:
            self._on_action_sent(command)
