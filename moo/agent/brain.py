"""
Brain: perception-action loop for moo-agent.

Receives server output via enqueue_output(), checks reflexive rules first, then
falls back to LLM inference. Supports append-only soul evolution via
SOUL_PATCH_RULE: / SOUL_PATCH_VERB: directives in LLM responses.

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
from anthropic import AsyncAnthropic, AsyncAnthropicBedrock

from moo.agent.soul import Soul, append_patch, compile_rules, parse_soul


class Status(enum.Enum):
    READY = "ready"  # idle, waiting for events
    SLEEPING = "sleeping"  # LLM call in flight or wakeup timer <30 s away
    THINKING = "thinking"  # actively processing an event


_PATCH_RULE_RE = re.compile(r"^SOUL_PATCH_RULE:\s*(.+)$")
_PATCH_VERB_RE = re.compile(r"^SOUL_PATCH_VERB:\s*(.+)$")
_COMMAND_RE = re.compile(r"^COMMAND:\s*(.+)$")
_GOAL_RE = re.compile(r"^GOAL:\s*(.+)$")
_PLAN_RE = re.compile(r"^PLAN:\s*(.+)$")
_ARROW_RE = re.compile(r"\s*->\s*")

_PATCH_INSTRUCTIONS = """\
Respond using this structure. Put any reasoning on lines before GOAL: — those
lines are visible to you but never sent to the server.

GOAL: <one-line statement of your current objective>
PLAN: <step 1> | <step 2> | <step 3>   (optional; list the next few commands)
COMMAND: <single MOO command to execute right now>

Example:
The key must be somewhere in the north wing. I'll search room by room.
GOAL: find the brass key
PLAN: go north | look | take key
COMMAND: go north

Update GOAL whenever your objective changes. Include PLAN when you have a clear
multi-step sequence to follow — show the remaining steps each turn so you stay
on track. Drop PLAN when the sequence is complete.

You may also propose soul patches before COMMAND::
SOUL_PATCH_RULE: ^You arrive -> look
SOUL_PATCH_VERB: check_exits -> @exits
GOAL: explore the manor
COMMAND: go north

Only propose a patch when you have encountered the same situation multiple times
and a fixed response is clearly correct."""

_SUMMARIZE_SYSTEM = (
    "Summarize the following MOO game session log in 2-3 concise sentences. "
    "Be specific: include locations visited, objects found or used, and notable events."
)


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
    ):
        self._soul = soul
        self._config = config
        self._send_command = send_command
        self._on_thought = on_thought
        self._config_dir = config_dir
        self._on_status_change = on_status_change

        self._output_queue: asyncio.Queue[str] = asyncio.Queue()
        self._window: collections.deque[str] = collections.deque(maxlen=config.agent.memory_window_lines)
        self._compiled_rules = compile_rules(soul)
        self._limiter = LeakyBucketLimiter(config.agent.command_rate_per_second)
        self._llm_sem = asyncio.Semaphore(1)
        self._summary_sem = asyncio.Semaphore(1)
        self._status = Status.READY
        self._last_activity = time.monotonic()

        # Persistent planning state — carried forward in every LLM call
        self._current_goal: str = prior_goal
        self._current_plan: list[str] = []
        self._memory_summary: str = prior_session_summary

    def _set_status(self, status: Status) -> None:
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
        """Construct the user-turn message for the LLM, including memory and planning state."""
        parts = []
        if self._memory_summary:
            parts.append(f"[Earlier context: {self._memory_summary}]")
        if self._current_goal:
            parts.append(f"Current goal: {self._current_goal}")
        if self._current_plan:
            parts.append(f"Remaining plan: {' | '.join(self._current_plan)}")
        parts.append("\n".join(self._window))
        parts.append("\nWhat should you do next?")
        return "\n".join(parts)

    async def run(self) -> None:
        """Main perception-action loop. Runs until cancelled."""
        asyncio.get_event_loop().create_task(self._wakeup_loop())
        while True:
            text = await self._output_queue.get()
            self._set_status(Status.THINKING)
            self._window.append(text)

            window_max = self._window.maxlen or 50
            if len(self._window) >= window_max - 10:
                asyncio.get_event_loop().create_task(self._summarize_window())

            matched = self._check_rules(text)
            if matched:
                await self._dispatch(matched)
                self._set_status(Status.READY)
            else:
                asyncio.get_event_loop().create_task(self._llm_cycle())

    async def _wakeup_loop(self) -> None:
        """
        Idle wakeup timer. Fires an LLM cycle when no input has arrived for
        idle_wakeup_seconds. Switches status to WAIT when within 30 s of firing
        so the TUI can show the countdown pressure.
        """
        wakeup_s = self._config.agent.idle_wakeup_seconds
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
                asyncio.get_event_loop().create_task(self._llm_cycle())

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

    def _make_client(self) -> AsyncAnthropic | AsyncAnthropicBedrock:
        """Return an API client for the configured LLM provider."""
        if self._config.llm.provider == "bedrock":
            return AsyncAnthropicBedrock(aws_region=self._config.llm.aws_region)
        api_key = os.environ.get(self._config.llm.api_key_env, "")
        return AsyncAnthropic(api_key=api_key)

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

            client = self._make_client()
            try:
                resp = await client.messages.create(
                    model=self._config.llm.model,
                    max_tokens=150,
                    system=_SUMMARIZE_SYSTEM,
                    messages=[{"role": "user", "content": "\n".join(to_summarize)}],
                )
            except Exception:  # pylint: disable=broad-exception-caught
                return

            summary = resp.content[0].text.strip() if resp.content else ""
            if not summary:
                return

            self._memory_summary = summary
            self._window.clear()
            self._window.append(f"[Earlier: {summary}]")
            for line in remaining:
                self._window.append(line)

    async def _llm_cycle(self) -> None:
        """Single LLM inference cycle. Skips if another call is already in flight."""
        if self._llm_sem.locked():
            return
        self._set_status(Status.THINKING)
        async with self._llm_sem:
            client = self._make_client()

            prompt_parts = [self._soul.mission, self._soul.persona]
            if self._soul.context:
                prompt_parts.append(self._soul.context)
            prompt_parts.append(_PATCH_INSTRUCTIONS)
            system_prompt = "\n\n".join(prompt_parts)
            user_message = self._build_user_message()

            try:
                resp = await client.messages.create(
                    model=self._config.llm.model,
                    max_tokens=512,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_message}],
                )
            except Exception as exc:  # pylint: disable=broad-exception-caught
                self._on_thought(f"[LLM error] {exc}")
                self._set_status(Status.READY)
                return

            response_text = resp.content[0].text if resp.content else ""
            command_line = None
            thought_lines = []

            for line in response_text.splitlines():
                patch_rule = _PATCH_RULE_RE.match(line)
                patch_verb = _PATCH_VERB_RE.match(line)
                cmd_match = _COMMAND_RE.match(line)
                goal_match = _GOAL_RE.match(line)
                plan_match = _PLAN_RE.match(line)

                if goal_match:
                    new_goal = goal_match.group(1).strip()
                    if new_goal != self._current_goal:
                        self._current_goal = new_goal
                        self._on_thought(f"[Goal] {new_goal}")
                elif plan_match:
                    self._current_plan = [s.strip() for s in plan_match.group(1).split("|") if s.strip()]
                elif patch_rule:
                    self._apply_patch("rule", patch_rule.group(1))
                elif patch_verb:
                    self._apply_patch("verb", patch_verb.group(1))
                elif cmd_match:
                    command_line = cmd_match.group(1).strip()
                else:
                    thought_lines.append(line)

            thought = "\n".join(thought_lines).strip()
            if thought:
                self._on_thought(thought)

            # Fall back to full response if LLM didn't use COMMAND: prefix yet
            if not command_line:
                command_line = thought_lines[-1].strip() if thought_lines else ""

            if not command_line:
                self._set_status(Status.READY)
                return

            self._set_status(Status.THINKING)
            command = self._resolve_intent(command_line)
            await self._dispatch(command)
            self._set_status(Status.READY)

    def _apply_patch(self, entry_type: str, directive: str) -> None:
        """Parse a patch directive and append to SOUL.patch.md, then reload rules."""
        parts = _ARROW_RE.split(directive, maxsplit=1)
        if len(parts) != 2:
            return
        pattern_or_intent, command = parts[0].strip(), parts[1].strip()
        if not pattern_or_intent or not command:
            return

        if self._config_dir:
            append_patch(self._config_dir, entry_type, pattern_or_intent, command)
            # Reload the operational layer and recompile
            try:
                updated = parse_soul(self._config_dir)
                self._soul.rules = updated.rules
                self._soul.verb_mappings = updated.verb_mappings
                self._compiled_rules = compile_rules(self._soul)
            except Exception:  # pylint: disable=broad-exception-caught
                pass

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
