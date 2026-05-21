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

from asynciolimiter import LeakyBucketLimiter
from anthropic import APIStatusError
from instructor.core import InstructorRetryException

from moo.agent.brain.chain import process_server_text, _is_page
from moo.agent.brain.prompt import (
    SUMMARIZE_SYSTEM as _SUMMARIZE_SYSTEM,
    build_system_prompt,
    build_user_message,
)
from moo.agent.brain.plans import (
    load_latest_build_plan,
    load_traversal_plan,
    save_build_plan,
    save_traversal_plan,
)
from moo.agent.brain.state import BrainState
from moo.agent.llm_client import call_llm, make_client, summarize
from moo.agent.response_model import Action, AgentResponse
from moo.agent.soul import Soul, append_patch_directive, compile_rules, parse_soul
from moo.agent.tools import SYSTEM_TOOLS, ToolSpec, get_tool


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


def looks_like_error(text: str) -> bool:
    first_line = text.lstrip().split("\n")[0]
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
        send_command: Callable[[str], None],
        on_thought: Callable[[str], None],
        config_dir: Path | None = None,
        on_status_change: Callable[[Status], None] | None = None,
        prior_session_summary: str = "",
        prior_goal: str = "",
        tools: list[ToolSpec] | None = None,
    ):
        self._soul = soul
        self._config = config
        self._send_command = send_command
        self._on_thought = on_thought
        self._config_dir = config_dir
        self._on_status_change = on_status_change
        # raw + respond are always available, regardless of per-agent config.
        configured = tools or []
        configured_names = {t.name for t in configured}
        self._tools: list[ToolSpec] = configured + [t for t in SYSTEM_TOOLS if t.name not in configured_names]

        self._output_queue: asyncio.Queue[str] = asyncio.Queue()
        self._window: collections.deque[str] = collections.deque(maxlen=config.agent.memory_window_lines)
        self._compiled_rules = compile_rules(soul)
        self._limiter = LeakyBucketLimiter(config.agent.command_rate_per_second)
        self._llm_sem = asyncio.Semaphore(1)
        self._summary_sem = asyncio.Semaphore(1)
        self._status = Status.WAITING if config.agent.idle_wakeup_seconds == 0 else Status.READY
        self._last_activity = time.monotonic()
        self._script_queue: list[str] = []
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

        # Single client to keep LM Studio's KV cache warm across cycles.
        self._client = make_client(config.llm)

        chain_lower = [a.lower() for a in config.agent.token_chain]
        self._is_orchestrator = bool(chain_lower) and (config.ssh.user or "").lower() not in chain_lower

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
        Loop, Script Queue.

        Quiet-period semantics: the 0.3 s timeout edge is what makes Celery
        print() preamble bursts settle into a single drain step rather than
        racing through the queue line-by-line.
        """
        if self._config.agent.idle_wakeup_seconds > 0:
            asyncio.create_task(self._wakeup_loop())
        if self._config.agent.stall_timeout_seconds > 0:
            asyncio.create_task(self._stall_check_loop())
        pending_llm = False
        pending_drain = False
        while True:
            try:
                text = await asyncio.wait_for(self._output_queue.get(), timeout=0.3)
            except asyncio.TimeoutError:
                if pending_drain:
                    pending_drain = False
                    self._drain_script()
                    self._set_status(Status.READY if not self._script_queue else Status.THINKING)
                    if self._script_queue:
                        pending_drain = True
                    elif not pending_llm and not self._is_orchestrator and not self._config.agent.timer_only:
                        page_triggered_idle = (
                            self._config.agent.idle_wakeup_seconds == 0 and not self._state.current_goal
                        )
                        if not page_triggered_idle:
                            pending_llm = True
                elif self._script_queue and self._status != Status.THINKING:
                    # Fallback drain: Celery verbs whose print() output arrives
                    # after PREFIX/SUFFIX never reach run(), so pending_drain
                    # never gets set. See agent-internals: The Fallback Drain.
                    self._drain_script()
                    self._set_status(Status.READY if not self._script_queue else Status.THINKING)
                    if self._script_queue:
                        pending_drain = True
                    elif not pending_llm and not self._is_orchestrator and not self._config.agent.timer_only:
                        page_triggered_idle = (
                            self._config.agent.idle_wakeup_seconds == 0 and not self._state.current_goal
                        )
                        if not page_triggered_idle:
                            pending_llm = True
                elif pending_llm:
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
                self._script_queue.insert(0, cmd)
            self._script_queue.extend(actions.scripts)
            for thought in actions.thoughts:
                self._on_thought(thought)
            if actions.save_traversal_plan:
                self._save_traversal_plan()
            if actions.skip:
                continue

            window_max = self._window.maxlen or 50
            if len(self._window) >= window_max - 10:
                asyncio.create_task(self._summarize_window())

            # While a script is running, defer the drain until the burst
            # settles (see agent-internals: Why drain after a quiet period).
            if self._script_queue:
                if looks_like_error(text):
                    self._script_queue.clear()
                    self._on_thought("[Script] Error detected — returning control to LLM.")
                    pending_drain = False
                    pending_llm = True
                else:
                    pending_drain = True
                self._set_status(Status.READY if not self._script_queue else Status.THINKING)
                continue

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
            command = f"page {agent} with Stall alert: you hold the token. Resume your work and send done."
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

    async def _call_llm(self, system: str, user_message: str, max_tokens: int) -> AgentResponse:
        """Thin instance-method shim around ``llm_client.call_llm``."""
        return await call_llm(
            self._client,
            self._config.llm,
            system,
            user_message,
            max_tokens,
            temperature=self._config.agent.temperature,
            top_p=self._config.agent.top_p,
            top_k=self._config.agent.top_k,
            max_retries=self._config.agent.instructor_retries,
        )

    async def _summarize_window(self) -> None:
        """Condense the oldest half of the rolling window. Skip-on-busy."""
        if self._summary_sem.locked():
            return
        async with self._summary_sem:
            window_max = self._window.maxlen or 50
            n = window_max // 2
            if len(self._window) < n:
                return

            lines = list(self._window)
            to_summarize = lines[:n]
            remaining = lines[n:]

            try:
                summary = await summarize(
                    self._client, self._config.llm, _SUMMARIZE_SYSTEM, "\n".join(to_summarize), 150
                )
            except Exception:  # pylint: disable=broad-exception-caught
                return

            summary = summary.strip()
            if not summary:
                return

            self._state.memory_summary = summary
            self._window.clear()
            self._window.append(f"[Earlier: {summary}]")
            for line in remaining:
                self._window.append(line)

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
            system_prompt = build_system_prompt(self._soul, self._tools)
            user_message = self._build_user_message()

            resp = await self._run_llm_with_retry(system_prompt, user_message)
            if resp is None:
                self._emit_cycle_stats(cycle_start, tool_calls=0, command_line=None)
                self._set_status(Status.READY)
                return

            tool_calls_count = self._apply_agent_response(resp)

            if resp.reasoning:
                self._on_thought(resp.reasoning)

            # Kick off the first queued command immediately; the rest drain via run().
            command_line = self._script_queue.pop(0) if self._script_queue else None

            if not command_line:
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
                    # Final escalation: 3 zero-action cycles in a row.
                    # Inject an explicit operator nudge and grant one more
                    # cycle so the agent has a chance to recover by paging
                    # Foreman + calling done() instead of stalling silently.
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
                self._emit_cycle_stats(cycle_start, tool_calls=tool_calls_count, command_line=None)
                self._set_status(Status.READY)
                return

            self._emit_cycle_stats(cycle_start, tool_calls=tool_calls_count, command_line=command_line)
            self._set_status(Status.THINKING)
            command = self._resolve_intent(command_line)
            await self._dispatch(command)
            self._set_status(Status.READY)

    def _emit_cycle_stats(
        self,
        cycle_start: float,
        *,
        tool_calls: int,
        command_line: str | None,
    ) -> None:
        duration = time.monotonic() - cycle_start
        commands = len(self._script_queue) + (1 if command_line else 0)
        self._on_thought(f"[Cycle] duration={duration:.1f}s tool_calls={tool_calls} commands={commands}")

    async def _run_llm_with_retry(self, system_prompt: str, user_message: str) -> AgentResponse | None:
        """
        Call the LLM with 529-overload retries (5 s, 10 s, 20 s backoff).
        An exhausted Instructor retry budget surfaces as None so ``_llm_cycle``
        falls through to the goal-only recovery-nudge path.
        """
        for attempt in range(4):
            try:
                return await self._call_llm(system_prompt, user_message, self._config.agent.max_tokens)
            except APIStatusError as exc:
                if exc.status_code == 529 and attempt < 3:
                    delay = 5 * 2**attempt
                    self._on_thought(f"[LLM overloaded] retrying in {delay}s (attempt {attempt + 1}/3)")
                    await asyncio.sleep(delay)
                    continue
                self._on_thought(f"[LLM error] {exc}")
                return None
            except InstructorRetryException as exc:
                self._on_thought(f"[LLM] structured-output validation failed after retries — {exc}")
                return None
            except Exception as exc:  # pylint: disable=broad-exception-caught
                self._on_thought(f"[LLM error] {exc}")
                return None
        return None

    def _apply_agent_response(self, resp: AgentResponse) -> int:
        """
        Apply a validated ``AgentResponse``: goal, soul patches, build plan,
        actions, and the completion signal. Returns the action count for
        cycle stats.
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

        n_actions = self._dispatch_actions(resp.actions)

        # The `done` field is processed after actions so a final `page foreman`
        # in the same response can satisfy the foreman-paged guard first.
        if resp.done is not None:
            self._handle_done(resp.done)

        return n_actions

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

    def _dispatch_actions(self, actions: list[Action]) -> int:
        """
        Dedupe and translate validated actions into queued MOO commands. The
        translated commands replace ``_script_queue``; the first is dispatched
        by ``_llm_cycle`` and the rest drain via ``run()``.
        """
        if not actions:
            return 0

        # Some models (Gemma 4) emit duplicate actions in one response.
        seen: list[tuple[str, str]] = []
        deduped: list[Action] = []
        for action in actions:
            key = (action.tool, str(sorted(action.args.items())))
            if key not in seen:
                seen.append(key)
                deduped.append(action)

        queued: list[str] = []
        for action in deduped:
            tool_name, tool_args = action.tool, action.args
            spec = get_tool(self._tools, tool_name)
            if spec is None:
                self._on_thought(f"[Tool] Unknown tool '{tool_name}' — skipping.")
                continue
            if tool_name == "respond":
                message = tool_args.get("message", "").strip()
                if message:
                    self._on_thought(f"[Respond] {message}")
                continue
            if tool_name == "done":
                self._handle_done(tool_args.get("summary", ""))
                continue
            if tool_name == "teleport":
                dest = str(tool_args.get("destination", "")).strip()
                if self._is_redundant_teleport(dest):
                    # Inject into the window so the LLM sees the skip and
                    # advances to the next plan step — see agent-internals:
                    # Redundant-teleport suppression.
                    msg = (
                        f"[Tool] Skipping teleport({dest}) — already in "
                        f"{self._state.current_room_name} ({self._state.current_room_id})."
                    )
                    self._on_thought(msg)
                    self._window.append(msg)
                    self._window.append(
                        "[Tool] You are already at the destination. Pick the "
                        "next step from your plan instead of teleporting."
                    )
                    continue
            if tool_name == "page":
                message = tool_args.get("message", "")
                target = tool_args.get("target", "")
                if "Token:" in message and target and target.lower() != "foreman":
                    self._state.token_dispatched_at = time.monotonic()
                    self._state.token_dispatched_to = target
                    self._on_thought(f"[Stall] Token dispatched to {target} — stall timer started.")
                if "Token:" in message and target and target.lower() == "foreman" and "done" in message.lower():
                    self._state.foreman_paged = True
            try:
                commands = spec.translate(tool_args)
            except KeyError as exc:
                self._on_thought(f"[server_error] Tool '{tool_name}' missing required argument {exc} — skipping.")
                continue
            except ValueError as exc:
                self._on_thought(f"[server_error] Tool '{tool_name}' rejected: {exc}")
                self._window.append(f"[Operator]: {exc}")
                continue
            queued.extend(commands)
            self._on_thought(f"[Tool] {tool_name}({tool_args})")
        if queued:
            self._script_queue = queued
        return len(deduped)

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

    def _is_redundant_teleport(self, dest: str) -> bool:
        """True when `dest` names the room we're already in (by id or name)."""
        if not dest:
            return False
        here_id = self._state.current_room_id
        here_name = self._state.current_room_name
        if not here_id:
            return False
        return dest == here_id or (bool(here_name) and dest.lower() == here_name.lower())

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

    def _drain_script(self) -> bool:
        """
        Advance the script queue by one step. Called from run() after the
        quiet-period edge — see agent-internals: Why drain after a quiet
        period. Returns True if a command was dispatched.
        """
        if not self._script_queue:
            return False
        next_cmd = self._script_queue.pop(0)
        self._window.append(f"> {next_cmd}")
        self._send_command(next_cmd)
        self._check_command_loop(next_cmd)
        return True

    async def _dispatch(self, command: str) -> None:
        """
        Rate-limited command dispatch. The window log entry lets the LLM
        correlate server responses with what was sent.
        """
        if not command.strip():
            return
        await self._limiter.wait()
        self._window.append(f"> {command}")
        self._send_command(command)
        self._check_command_loop(command)
