"""
Brain: perception-action loop for moo-agent.

Receives server output via enqueue_output(), checks reflexive rules first, then
falls back to LLM inference. Supports append-only soul evolution via
SOUL_PATCH_RULE: / SOUL_PATCH_VERB: directives in LLM responses.

When a tools list is supplied, the Anthropic/Bedrock path uses native tool use
to obtain structured ToolSpec calls instead of parsing free-form COMMAND:/SCRIPT:
text. LM Studio falls back to TOOL: string parsing. The COMMAND:/SCRIPT: syntax
is retained as a fallback when no tools are configured.

Does not import from moo.core or trigger Django setup.
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

from moo.agent.brain.chain import process_server_text, _is_page
from moo.agent.brain.directives import parse_llm_response
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
from moo.agent.llm_client import call_llm, make_client
from moo.agent.soul import Soul, append_patch_directive, compile_rules, parse_soul
from moo.agent.tools import LLMResponse, ToolSpec, get_tool, parse_json_tool_block, parse_tool_line


class Status(enum.Enum):
    READY = "ready"  # idle, waiting for events (timer-based agents)
    WAITING = "waiting"  # idle, waiting for the next page/token (page-triggered agents)
    SLEEPING = "sleeping"  # LLM call in flight or wakeup timer <30 s away
    THINKING = "thinking"  # actively processing an event


_SCRIPT_RE = re.compile(r"^SCRIPT:\s*(.+)$")


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
    "<|",  # Gemma special tokens leaking into commands (e.g. <|tool_response>)
    "Go where?",  # tried to go a direction with no exit
    "Usage:",  # missing required syntax (e.g. @reply without `with`)
    "When you say,",  # ambiguous object name — @create and other commands silently fail
    "More than one object defines",  # verb dispatch ambiguity — command failed to execute
    "That alias",  # alias already exists on this object — @alias is a no-op
)


def looks_like_error(text: str) -> bool:
    first_line = text.lstrip().split("\n")[0]
    return any(first_line.startswith(p) for p in _ERROR_PREFIXES)


class Brain:
    """
    Async perception-action loop.

    Wired to a MooConnection via enqueue_output() and send_command callbacks.
    Reflexive rules bypass the LLM for immediate dispatch. LLM inference uses
    a skip-on-busy semaphore so rapid output never queues multiple API calls.

    Goal and plan are persisted across LLM calls so the agent maintains
    continuity of intent. A background summarization task condenses the oldest
    portion of the rolling window when it nears capacity.
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
        self._tools: list[ToolSpec] = tools or []

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

        # All per-session mutable state lives on self._state. Infrastructure
        # fields (queue, window, rules, client, etc.) stay on Brain above.
        # In page-triggered mode (idle_wakeup_seconds == 0), ignore prior_goal so
        # the agent always starts cold and waits for a token page rather than
        # immediately resuming the previous session's work. If the prior goal
        # was non-empty, stash it in prior_goal_for_reconnect so the agent can
        # auto-page the orchestrator on connect.
        page_triggered = self._config.agent.idle_wakeup_seconds == 0
        self._state = BrainState(
            current_goal="" if page_triggered else prior_goal,
            prior_goal_for_reconnect=prior_goal if page_triggered else "",
            memory_summary=prior_session_summary,
        )

        # Reload the most recent build plan on startup so the agent doesn't
        # re-plan from scratch after a restart. Page-triggered agents always
        # start cold and receive fresh room lists via the token; loading a
        # stale traversal plan from disk lets the LLM skip divine() on the
        # next token pass and visit last session's rooms instead.
        self._load_latest_build_plan()
        if not self._state.current_plan and not page_triggered:
            self._load_traversal_plan()

        # Single client instance reused for the lifetime of the Brain so that
        # LM Studio (and other servers) can maintain a warm KV cache across calls.
        self._client = make_client(config.llm)

        chain_lower = [a.lower() for a in config.agent.token_chain]
        self._is_orchestrator = bool(chain_lower) and (config.ssh.user or "").lower() not in chain_lower

    def _set_status(self, status: Status) -> None:
        # Page-triggered agents (idle_wakeup_seconds == 0) show "waiting" when idle
        # so the prompt reflects that they are waiting for the next token/page.
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
        """
        Called when the operator types an instruction in the TUI.

        The text is added to the rolling window as an operator message and an
        LLM cycle is forced immediately — rule matching is skipped because a
        direct instruction should always reach the LLM.
        """
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
        """Main perception-action loop. Runs until cancelled."""
        if self._config.agent.idle_wakeup_seconds > 0:
            asyncio.create_task(self._wakeup_loop())
        if self._config.agent.stall_timeout_seconds > 0:
            asyncio.create_task(self._stall_check_loop())
        pending_llm = False
        pending_drain = False  # set True when output arrives while script is queued
        while True:
            try:
                text = await asyncio.wait_for(self._output_queue.get(), timeout=0.3)
            except asyncio.TimeoutError:
                # Quiet period expired — flush pending script drain or LLM cycle.
                # Script drain takes priority: fire the next command only after
                # the full response burst has settled, preventing Celery print()
                # preamble lines from advancing the queue multiple times per response.
                if pending_drain:
                    pending_drain = False
                    self._drain_script()
                    self._set_status(Status.READY if not self._script_queue else Status.THINKING)
                    # If the script still has commands, keep pending_drain=True so that
                    # a silent command (no server output) doesn't stall the loop forever.
                    if self._script_queue:
                        pending_drain = True
                    elif not pending_llm and not self._is_orchestrator and not self._config.agent.timer_only:
                        # Script just finished with no pending LLM — fire LLM to evaluate
                        # results. Needed when the final command is silent (no server output).
                        # Orchestrators skip this: their token relay is deterministic
                        # and a post-drain LLM cycle just burns tokens inventing goals.
                        # In page-triggered mode with no active goal, suppress the LLM —
                        # the script was infrastructure (e.g. auto-reconnect page) and
                        # there is nothing to evaluate until the token page arrives.
                        # timer_only agents: LLM fires only via the wakeup timer, never on output.
                        page_triggered_idle = (
                            self._config.agent.idle_wakeup_seconds == 0 and not self._state.current_goal
                        )
                        if not page_triggered_idle:
                            pending_llm = True
                elif self._script_queue and self._status != Status.THINKING:
                    # Fallback drain: the script queue has commands but no server output
                    # arrived to set pending_drain. This happens for Celery-based verbs
                    # (@create, @obvious, @alias, etc.) whose print() output arrives after
                    # the PREFIX/SUFFIX window and never reaches run(). Without this path,
                    # only the first command per LLM cycle executes; the rest wait until
                    # the idle wakeup fires a new LLM cycle, discarding the queue.
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
                        # session_done blocks the pending_llm path, but we must still
                        # reset status to READY so the wakeup loop can fire. Without this,
                        # status stays THINKING and the wakeup loop skips indefinitely.
                        self._set_status(Status.READY)
                continue

            self._set_status(Status.THINKING)
            self._window.append(text)
            self._state.idle_wakeup_count = 0  # real server output arrived — reset stall counter
            self._state.goal_only_count = 0  # real output resets the goal-stall counter

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

            # If a script is running, accumulate output and drain after the burst
            # settles (0.3 s of quiet). Celery print() output arrives as multiple
            # individual preamble lines; calling drain on each line would send
            # many commands at once instead of one per response cycle.
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
                # Don't fire the LLM immediately — mark as pending and wait for
                # the burst to settle (0.3 s of quiet) before calling the LLM.
                # This lets multi-line tell() responses (e.g. @audit) fully
                # arrive before the LLM snapshot is taken.
                #
                # In "page-triggered" mode (idle_wakeup_seconds == 0), suppress
                # LLM cycles while waiting for the token page. Once the agent
                # has a current goal (token received, work started), treat it
                # like a normal agent and fire on all server output.
                if self._config.agent.idle_wakeup_seconds == 0 and not self._state.current_goal and not _is_page(text):
                    self._set_status(Status.READY)  # waiting for token; show waiting> prompt
                elif self._is_orchestrator:
                    pass  # orchestrator: LLM fires via timer/operator only; brain.py handles relay
                elif self._config.agent.timer_only:
                    self._set_status(Status.READY)  # timer_only: no LLM on output; let wakeup timer handle it
                elif not self._state.session_done:
                    pending_llm = True

    async def _wakeup_loop(self) -> None:
        """
        Idle wakeup timer. Fires an LLM cycle when no input has arrived for
        idle_wakeup_seconds. Switches status to WAIT when within 30 s of firing
        so the TUI can show the countdown pressure.
        """
        wakeup_s = self._config.agent.idle_wakeup_seconds
        if wakeup_s == 0:
            return  # page-triggered mode: never fire timer-based LLM cycles
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
                # Don't fire idle wakeups after the plan is done — the agent
                # has nothing left to do and would just invent extra work.
                # Also skip if done() was called — session is finished.
                if not (self._state.plan_exhausted and not self._state.current_goal) and not self._state.session_done:
                    self._state.idle_wakeup_count += 1
                    # Timer-based agents clear their goal on each wakeup to
                    # prevent stale done/recap loops. Optionally also clear the
                    # rolling window — agents that need room context between
                    # wakeups (e.g. reactive NPCs) can set clear_window_on_wakeup=false.
                    if self._config.agent.clear_window_on_wakeup:
                        self._window.clear()
                    self._state.current_goal = ""
                    asyncio.create_task(self._llm_cycle())

    async def _stall_check_loop(self) -> None:
        """
        Deterministic stall detector. Re-pages the token-holding agent if it
        has not returned a done page within stall_timeout_seconds.

        Bypasses the LLM entirely — runs only when stall_timeout_seconds > 0.
        Checks every 30 s; fires a re-page at each multiple of the timeout.
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
            # Backoff: wait another stall_s before the next alert.
            self._state.token_dispatched_at = time.monotonic()

    async def _target_is_actively_cycling(self, agent: str, stall_s: int) -> bool:
        """
        Shell out to `agentmux cycle-age` for `agent` and decide whether it
        is still inside a plausible cycle (age < max(stall_s, 3×p95)).

        Returns False — fall through to the existing re-page path — when the
        env vars aren't set, the subprocess fails, or the agent has too few
        samples for a meaningful p95. This keeps behavior backward-compatible.
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

    async def _call_llm(self, client, system: str, user_message: str, max_tokens: int) -> LLMResponse:
        """Thin instance-method shim around ``llm_client.call_llm``."""
        return await call_llm(
            client,
            self._config.llm,
            self._tools,
            system,
            user_message,
            max_tokens,
            temperature=self._config.agent.temperature,
        )

    async def _summarize_window(self) -> None:
        """
        Condense the oldest half of the rolling window into a summary sentence.

        Runs as a background task when the window nears capacity. Skip-on-busy
        via _summary_sem so only one summarization runs at a time.
        """
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
                llm_resp = await self._call_llm(self._client, _SUMMARIZE_SYSTEM, "\n".join(to_summarize), 150)
            except Exception:  # pylint: disable=broad-exception-caught
                return

            summary = llm_resp.text.strip()
            if not summary:
                return

            self._state.memory_summary = summary
            self._window.clear()
            self._window.append(f"[Earlier: {summary}]")
            for line in remaining:
                self._window.append(line)

    async def _llm_cycle(self) -> None:
        """Single LLM inference cycle. Skips if another call is already in flight."""
        if self._llm_sem.locked():
            return
        # Emit any script completion summary now — all output has settled.
        if self._state.pending_done_msg:
            self._on_thought(self._state.pending_done_msg)
            self._state.pending_done_msg = ""
        self._set_status(Status.THINKING)
        cycle_start = time.monotonic()

        async with self._llm_sem:
            system_prompt = build_system_prompt(self._soul, tools_active=bool(self._tools))
            user_message = self._build_user_message()

            llm_resp = await self._run_llm_with_retry(system_prompt, user_message)
            if llm_resp is None:
                self._emit_cycle_stats(cycle_start, tool_calls=0, script_lines=0, command_line=None)
                self._set_status(Status.READY)
                return

            parsed = parse_llm_response(llm_resp.text)
            command_line, script_lines = self._apply_parsed_response(parsed)
            tool_calls_count = self._dispatch_tool_calls(llm_resp.tool_calls)

            thought = "\n".join(parsed.thought_lines).strip()
            if thought:
                self._on_thought(thought)

            # If a script was queued and no explicit COMMAND: was given, kick off
            # the first step immediately. Remaining steps are drained by run() as
            # server output arrives.
            if self._script_queue and not command_line:
                command_line = self._script_queue.pop(0)
            elif not command_line and parsed.thought_lines:
                # Try JSON code block fallback before single-line bare-call fallback.
                # Some models emit OpenAI-style {"tool_calls": [...]} JSON in their
                # text content when structured tool calls aren't surfaced by the API.
                json_calls = parse_json_tool_block(parsed.thought_lines)
                if json_calls:
                    tool_calls_count += self._dispatch_tool_calls(json_calls)
                    if self._script_queue:
                        command_line = self._script_queue.pop(0)
                else:
                    command_line = self._try_bare_line_fallback(parsed.thought_lines)

            if not command_line:
                # If a goal was set but no action taken, fire one more LLM cycle to
                # act on it. This handles models (like Gemma) that split goal-setting
                # and action into separate responses. Cap at 3 to avoid infinite loops.
                # Orchestrators skip this entirely — they have nothing to "act on"
                # while waiting for a token holder; deterministic relay drives them.
                if (
                    self._state.current_goal
                    and not self._state.session_done
                    and not self._state.plan_exhausted
                    and not self._is_orchestrator
                    and self._state.goal_only_count < 3
                ):
                    self._state.goal_only_count += 1
                    asyncio.create_task(self._llm_cycle())
                self._emit_cycle_stats(
                    cycle_start,
                    tool_calls=tool_calls_count,
                    script_lines=script_lines,
                    command_line=None,
                )
                self._set_status(Status.READY)
                return

            self._emit_cycle_stats(
                cycle_start,
                tool_calls=tool_calls_count,
                script_lines=script_lines,
                command_line=command_line,
            )
            self._set_status(Status.THINKING)
            command = self._resolve_intent(command_line)
            await self._dispatch(command)
            self._set_status(Status.READY)

    def _emit_cycle_stats(
        self,
        cycle_start: float,
        *,
        tool_calls: int,
        script_lines: int,
        command_line: str | None,
    ) -> None:
        duration = time.monotonic() - cycle_start
        commands = len(self._script_queue) + (1 if command_line else 0)
        self._on_thought(
            f"[Cycle] duration={duration:.1f}s tool_calls={tool_calls} commands={commands} script_lines={script_lines}"
        )

    async def _run_llm_with_retry(self, system_prompt: str, user_message: str) -> LLMResponse | None:
        """
        Call the LLM with 529-overload retries (5s, 10s, 20s backoff).

        Returns the response on success, ``None`` if every attempt failed —
        any other exception is caught and logged as a thought, returning
        ``None`` as well. Callers must handle the ``None`` case (emit cycle
        stats, set status READY, return).
        """
        for attempt in range(4):
            try:
                return await self._call_llm(self._client, system_prompt, user_message, self._config.agent.max_tokens)
            except APIStatusError as exc:
                if exc.status_code == 529 and attempt < 3:
                    delay = 5 * 2**attempt  # 5, 10, 20 s
                    self._on_thought(f"[LLM overloaded] retrying in {delay}s (attempt {attempt + 1}/3)")
                    await asyncio.sleep(delay)
                    continue
                self._on_thought(f"[LLM error] {exc}")
                return None
            except Exception as exc:  # pylint: disable=broad-exception-caught
                self._on_thought(f"[LLM error] {exc}")
                return None
        return None

    def _apply_parsed_response(self, parsed) -> tuple[str | None, int]:
        """
        Apply each directive from a parsed LLM response.

        Mutates ``self._state``, ``self._script_queue``, and invokes patch /
        plan side effects. Returns ``(command_line, script_lines_count)`` for
        the cycle stats line and for the fallback logic downstream.
        """
        command_line: str | None = None
        script_lines = 0
        for directive in parsed.directives:
            if directive.kind == "goal":
                new_goal = directive.value
                if new_goal != self._state.current_goal:
                    self._state.current_goal = new_goal
                    self._on_thought(f"[Goal] {new_goal}")
            elif directive.kind == "plan":
                self._state.current_plan = [s.strip() for s in directive.value.split("|") if s.strip()]
                self._save_traversal_plan()
            elif directive.kind == "patch_rule":
                self._apply_patch("rule", directive.value)
            elif directive.kind == "patch_verb":
                self._apply_patch("verb", directive.value)
            elif directive.kind == "patch_note":
                self._apply_patch("note", directive.value)
            elif directive.kind == "build_plan":
                self._save_build_plan(directive.value)
            elif directive.kind == "script":
                self._handle_script_line(directive.value)
                script_lines += 1
            elif directive.kind == "done":
                self._state.pending_done_msg = directive.value
                self._state.current_goal = ""
            elif directive.kind == "command":
                command_line = directive.value
        return command_line, script_lines

    def _dispatch_tool_calls(self, tool_calls: list[tuple[str, dict]]) -> int:
        """
        Dedupe and translate structured tool calls into queued MOO commands.

        Returns the number of calls processed after dedup. Replaces
        ``self._script_queue`` with the translated commands when any queue
        them — native tool calls are authoritative over any SCRIPT: queue the
        text parser may have already set (some models emit both).
        """
        if not tool_calls:
            return 0

        # Dedup consecutive exact duplicates. Some models (Gemma 4) repeat
        # the same call list twice in one response.
        seen: list[tuple[str, str]] = []
        deduped: list[tuple[str, dict]] = []
        for call in tool_calls:
            key = (call[0], str(call[1]))
            if key not in seen:
                seen.append(key)
                deduped.append(call)

        queued: list[str] = []
        for tool_name, tool_args in deduped:
            spec = get_tool(self._tools, tool_name)
            if spec is None:
                self._on_thought(f"[Tool] Unknown tool '{tool_name}' — skipping.")
                continue
            if tool_name == "done":
                # Guard: done() is only allowed after page(target="foreman",
                # message="Token: ... done.") has been sent this session.
                # Agents that call done() before paging Foreman stall the chain
                # because session_done blocks all further LLM cycles.
                if not self._state.foreman_paged and not self._state.session_done:
                    agent_name = self._soul.name or "Agent"
                    self._on_thought(
                        f"[Done] Blocked — page Foreman first, then call done(). "
                        f"Your IMMEDIATE next action: "
                        f"page(target='foreman', message='Token: {agent_name} done.')"
                    )
                    self._state.current_goal = (
                        f"CRITICAL: call page(target='foreman', "
                        f"message='Token: {agent_name} done.') — this is your only next action"
                    )
                    continue
                summary = tool_args.get("summary", "").strip()
                self._state.pending_done_msg = summary
                self._state.current_goal = ""
                self._state.session_done = True
                if summary:
                    self._on_thought(f"[Done] {summary}")
                continue
            if tool_name == "page":
                message = tool_args.get("message", "")
                target = tool_args.get("target", "")
                if "Token:" in message and target and target.lower() != "foreman":
                    self._state.token_dispatched_at = time.monotonic()
                    self._state.token_dispatched_to = target
                    self._on_thought(f"[Stall] Token dispatched to {target} — stall timer started.")
                # Track that we've paged foreman with a done message so
                # done() guard knows the handoff was completed.
                if "Token:" in message and target and target.lower() == "foreman" and "done" in message.lower():
                    self._state.foreman_paged = True
            try:
                commands = spec.translate(tool_args)
            except KeyError as exc:
                self._on_thought(f"[server_error] Tool '{tool_name}' missing required argument {exc} — skipping.")
                continue
            queued.extend(commands)
            self._on_thought(f"[Tool] {tool_name}({tool_args})")
        if queued:
            # Replace any SCRIPT: queue set during text processing — native tool calls
            # are authoritative. Gemma models emit both a structured tool call AND a
            # SCRIPT: line in the same response, causing the same command to execute
            # twice if we prepend. Discard the text-based queue entirely.
            self._script_queue = queued
        return len(deduped)

    def _try_bare_line_fallback(self, thought_lines: list[str]) -> str | None:
        """
        Rescue a single-line LLM response that omitted COMMAND:/SCRIPT:.

        Returns the command to dispatch if the last thought line plausibly
        looks like a MOO command (or translates to one via the tool harness),
        otherwise ``None``. Multi-line prose, bare directive keywords, and
        parenthetical narrations are silently discarded to prevent the
        server's "Huh? I don't understand that command." cascade.
        """
        _BARE_DIRECTIVES = {"GOAL", "PLAN", "DONE", "SCRIPT", "COMMAND", "TOOL"}
        _MOO_COMMAND_PREFIXES = (
            "@",
            "say ",
            "page ",
            "look",
            "go ",
            "north",
            "south",
            "east",
            "west",
            "up",
            "down",
            "in ",
            "out ",
        )

        def _looks_like_moo_command(text: str) -> bool:
            return (
                text.startswith("@")
                or any(text.lower().startswith(p) for p in _MOO_COMMAND_PREFIXES)
                # Short lowercase phrases may be custom object verbs ("ring bell", "press plate").
                # Uppercase-first text is English prose ("Awaiting mason done page.") — skip it.
                or (len(text.split()) <= 4 and bool(text) and text[0].islower())
            )

        candidate = thought_lines[-1].strip()
        if not candidate:
            return None
        if len([line for line in thought_lines if line.strip()]) != 1:
            return None
        if candidate.upper() in _BARE_DIRECTIVES:
            return None
        if candidate.startswith("("):
            return None  # parenthetical narration like "(Wait mode)"

        # Try to translate bare tool-call syntax before sending as MOO command.
        tool_names = {t.name for t in self._tools} if self._tools else None
        parsed_candidate = parse_tool_line(candidate, known_names=tool_names)
        if parsed_candidate is None:
            return candidate if _looks_like_moo_command(candidate) else None

        spec = get_tool(self._tools, parsed_candidate[0])
        if spec is not None:
            translated = spec.translate(parsed_candidate[1])
            if translated:
                self._script_queue = translated + self._script_queue
                return self._script_queue.pop(0)
            if parsed_candidate[0] == "done":
                # done() produces no MOO commands but has critical side effects.
                # Same guard as the tool_calls path.
                if not self._state.foreman_paged and not self._state.session_done:
                    agent_name = self._soul.name or "Agent"
                    self._on_thought(
                        f"[Done] Blocked — page Foreman first, then call done(). "
                        f"Your IMMEDIATE next action: "
                        f"page(target='foreman', message='Token: {agent_name} done.')"
                    )
                    self._state.current_goal = (
                        f"CRITICAL: call page(target='foreman', "
                        f"message='Token: {agent_name} done.') — this is your only next action"
                    )
                    return None
                summary = parsed_candidate[1].get("summary", "").strip()
                self._state.pending_done_msg = summary
                self._state.current_goal = ""
                self._state.session_done = True
                if summary:
                    self._on_thought(f"[Done] {summary}")
            return None

        return candidate if _looks_like_moo_command(candidate) else None

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

    def _handle_script_line(self, line: str) -> None:
        """
        Parse a SCRIPT: directive and populate the script queue.

        Called from _llm_cycle when the LLM emits a SCRIPT: line. Each
        pipe-delimited step is queued for sequential dispatch by _drain_script
        without further LLM involvement.

        When tools are active, steps that look like bare tool function calls
        (e.g. move_object(obj="#44", destination="#41")) are expanded through
        the tool harness before queuing, so the server receives valid MOO commands.
        """
        m = _SCRIPT_RE.match(line)
        if not m:
            return
        raw_steps = [s.strip().strip("`") for s in m.group(1).split("|") if s.strip()]
        if not raw_steps:
            return
        tool_names: set[str] | None = {t.name for t in self._tools} if self._tools else None
        steps: list[str] = []
        for step in raw_steps:
            parsed = parse_tool_line(step, known_names=tool_names)
            if parsed is not None:
                tool_name, tool_args = parsed
                spec = get_tool(self._tools, tool_name)
                if spec is not None:
                    expanded = spec.translate(tool_args)
                    steps.extend(expanded)
                    continue
            # Strip trailing "done." that the LLM appends to @tunnel commands
            if step.lower().startswith("@tunnel"):
                step = re.sub(r"\s+done\.?\s*$", "", step, flags=re.IGNORECASE)
            steps.append(step)
        if steps:
            n = len(steps)
            self._script_queue = steps
            self._state.pending_done_msg = f"[Script] 0/{n} remaining."
            self._on_thought(f"[Script] Queued {n} commands.")

    def _check_command_loop(self, cmd: str) -> None:
        """
        Detect repetitive command loops and inject an operator warning.

        Tracks the last 8 commands sent. If any command appears 3+ times in
        that window the agent is almost certainly stuck (e.g. teleporting to
        the same room repeatedly). Inject a warning into the rolling window so
        the next LLM cycle sees it and tries a different approach. Resets the
        tracker after firing so the warning doesn't repeat on every command.
        """
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
        Advance the script queue by one step.

        Called from the run() timeout handler after a 0.3 s quiet period, so
        the full response burst (tell() blocks + Celery print() preamble lines)
        has settled before the next command is sent.

        Returns True if a command was dispatched, False if the queue was empty.
        Error detection is handled upstream in run() so that individual preamble
        lines do not each trigger a drain.
        """
        if not self._script_queue:
            return False
        next_cmd = self._script_queue.pop(0)
        self._window.append(f"> {next_cmd}")
        self._send_command(next_cmd)
        self._check_command_loop(next_cmd)
        return True

    async def _dispatch(self, command: str) -> None:
        """Rate-limited command dispatch. Skips blank commands."""
        if not command.strip():
            return
        await self._limiter.wait()
        # Record the command in the rolling window so subsequent LLM cycles
        # can correlate server output with what was sent. Without this the LLM
        # sees responses like "done" or "Description set for #44" with no
        # knowledge of which command produced them, causing unnecessary retries.
        self._window.append(f"> {command}")
        self._send_command(command)
        self._check_command_loop(command)
