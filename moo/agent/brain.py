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
from anthropic import APIStatusError, AsyncAnthropic, AsyncAnthropicBedrock

from moo.agent.soul import Soul, append_patch, compile_rules, parse_soul


class Status(enum.Enum):
    READY = "ready"  # idle, waiting for events
    SLEEPING = "sleeping"  # LLM call in flight or wakeup timer <30 s away
    THINKING = "thinking"  # actively processing an event


_PATCH_RULE_RE = re.compile(r"^SOUL_PATCH_RULE:\s*(.+)$")
_PATCH_VERB_RE = re.compile(r"^SOUL_PATCH_VERB:\s*(.+)$")
_COMMAND_RE = re.compile(r"^COMMAND:\s*(.+)$")
_SCRIPT_RE = re.compile(r"^SCRIPT:\s*(.+)$")
_DONE_RE = re.compile(r"^DONE:\s*(.+)$")
_GOAL_RE = re.compile(r"^GOAL:\s*(.+)$")
_PLAN_RE = re.compile(r"^PLAN:\s*(.+)$")
_ARROW_RE = re.compile(r"\s*->\s*")

_PATCH_INSTRUCTIONS = """\
Respond using ONLY this exact structure. Any reasoning goes on plain text lines
before GOAL:. Those lines are visible to you but never sent to the server.

For a single action:
GOAL: <one-line objective>
COMMAND: <single MOO command>

For a sequence of two or more actions, use SCRIPT: instead of COMMAND:. Steps
are pipe-delimited and execute one at a time as each server response arrives.
GOAL: <one-line objective>
SCRIPT: <cmd1> | <cmd2> | <cmd3>

When a goal is fully complete, emit DONE: to clear it and signal readiness:
GOAL: done
DONE: <one-line summary of what was accomplished>

Navigation note: @dig creates an exit but does NOT move you. After @dig, always
include a navigation step: SCRIPT: @dig north to "Room" | go north

Object ID note: After @create "name" from ..., reference the new object by its
quoted name in subsequent SCRIPT: steps — never use #N as a placeholder.
CORRECT: SCRIPT: @create "brass lamp" from "$thing" | @describe "brass lamp" as "..."
WRONG:   SCRIPT: @create "brass lamp" from "$thing" | @describe #N as "..."

GOOD example (multi-step build — ALL steps in one SCRIPT:):
GOAL: build and enter the library
SCRIPT: @dig north to "The Library" | go north | @describe here as "Tall shelves." | @create reading table

GOOD example (goal complete):
GOAL: done
DONE: Built the library with shelves and a reading table.

GOOD example (single step):
GOAL: look around
COMMAND: look

BAD example (splitting a build across multiple responses — do not do this):
[first response] SCRIPT: @dig north to "The Library" | go north
[next response]  SCRIPT: @describe here as "Tall shelves."

BAD example (markdown — do not do this):
**GOAL:** find the brass key
1. Go north
2. Look around
**COMMAND:** `go north`

Batch ALL steps needed to complete a goal into one SCRIPT: — do not split a
single build task across multiple responses.
DO NOT use markdown: no bold (**), no bullet points, no numbered lists, no
backticks around commands. The bare MOO command only — nothing else.
Emit exactly one COMMAND: or SCRIPT: per response — never both, never two
SCRIPT: lines. Do not quote or reproduce server output in your reasoning.

Update GOAL whenever your objective changes. You may also propose soul patches:
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
)


def _looks_like_error(text: str) -> bool:
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
        self._script_queue: list[str] = []
        self._pending_done_msg: str = ""

        # Persistent planning state — carried forward in every LLM call
        self._current_goal: str = prior_goal
        self._current_plan: list[str] = []
        self._memory_summary: str = prior_session_summary

        # Single client instance reused for the lifetime of the Brain so that
        # LM Studio (and other servers) can maintain a warm KV cache across calls.
        self._client = self._make_client()

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
                elif pending_llm:
                    pending_llm = False
                    asyncio.get_event_loop().create_task(self._llm_cycle())
                continue

            self._set_status(Status.THINKING)
            self._window.append(text)

            window_max = self._window.maxlen or 50
            if len(self._window) >= window_max - 10:
                asyncio.get_event_loop().create_task(self._summarize_window())

            # If a script is running, accumulate output and drain after the burst
            # settles (0.3 s of quiet). Celery print() output arrives as multiple
            # individual preamble lines; calling drain on each line would send
            # many commands at once instead of one per response cycle.
            if self._script_queue:
                if _looks_like_error(text):
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
                pending_llm = True

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

    def _make_client(self):
        """Return an API client for the configured LLM provider."""
        if self._config.llm.provider == "bedrock":
            return AsyncAnthropicBedrock(aws_region=self._config.llm.aws_region)
        if self._config.llm.provider == "lm_studio":
            from openai import AsyncOpenAI  # pylint: disable=import-outside-toplevel

            return AsyncOpenAI(
                base_url=self._config.llm.base_url or "http://localhost:1234/v1",
                api_key="lm-studio",
            )
        api_key = os.environ.get(self._config.llm.api_key_env, "")
        return AsyncAnthropic(api_key=api_key)

    async def _call_llm(self, client, system: str, user_message: str, max_tokens: int) -> str:
        """Make one LLM inference call and return the response text."""
        if self._config.llm.provider == "lm_studio":
            resp = await client.chat.completions.create(
                model=self._config.llm.model,
                max_tokens=max_tokens,
                extra_body={"enable_thinking": False},
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_message},
                ],
            )
            return resp.choices[0].message.content or ""
        resp = await client.messages.create(
            model=self._config.llm.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_message}],
        )
        return resp.content[0].text if resp.content else ""

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
                summary = await self._call_llm(self._client, _SUMMARIZE_SYSTEM, "\n".join(to_summarize), 150)
            except Exception:  # pylint: disable=broad-exception-caught
                return

            summary = summary.strip()
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
        # Emit any script completion summary now — all output has settled.
        if self._pending_done_msg:
            self._on_thought(self._pending_done_msg)
            self._pending_done_msg = ""
        self._set_status(Status.THINKING)
        async with self._llm_sem:
            prompt_parts = [self._soul.mission, self._soul.persona]
            if self._soul.context:
                prompt_parts.append(self._soul.context)
            prompt_parts.append(_PATCH_INSTRUCTIONS)
            if self._soul.addendum:
                prompt_parts.append(self._soul.addendum)
            system_prompt = "\n\n".join(prompt_parts)
            user_message = self._build_user_message()

            response_text = None
            for attempt in range(4):
                try:
                    response_text = await self._call_llm(
                        self._client, system_prompt, user_message, self._config.agent.max_tokens
                    )
                    break
                except APIStatusError as exc:
                    if exc.status_code == 529 and attempt < 3:
                        delay = 5 * 2**attempt  # 5, 10, 20 s
                        self._on_thought(f"[LLM overloaded] retrying in {delay}s (attempt {attempt + 1}/3)")
                        await asyncio.sleep(delay)
                    else:
                        self._on_thought(f"[LLM error] {exc}")
                        self._set_status(Status.READY)
                        return
                except Exception as exc:  # pylint: disable=broad-exception-caught
                    self._on_thought(f"[LLM error] {exc}")
                    self._set_status(Status.READY)
                    return
            if response_text is None:
                self._set_status(Status.READY)
                return
            command_line = None
            thought_lines = []

            for line in response_text.splitlines():
                # Strip markdown bold markers that some models emit around keywords
                # (e.g. "**COMMAND:** go north" → "COMMAND: go north")
                line = re.sub(r"^\*+\s*([A-Z_]+:)\s*\*+\s*", r"\1 ", line)
                patch_rule = _PATCH_RULE_RE.match(line)
                patch_verb = _PATCH_VERB_RE.match(line)
                cmd_match = _COMMAND_RE.match(line)
                script_match = _SCRIPT_RE.match(line)
                done_match = _DONE_RE.match(line)
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
                elif script_match:
                    self._handle_script_line(line)
                elif done_match:
                    self._pending_done_msg = done_match.group(1).strip()
                    self._current_goal = ""
                elif cmd_match:
                    command_line = cmd_match.group(1).strip().strip("`")
                else:
                    thought_lines.append(line)

            thought = "\n".join(thought_lines).strip()
            if thought:
                self._on_thought(thought)

            # If a script was queued and no explicit COMMAND: was given, kick off
            # the first step immediately. Remaining steps are drained by run() as
            # server output arrives.
            if self._script_queue and not command_line:
                command_line = self._script_queue.pop(0)
            elif not command_line and thought_lines:
                # Fallback: if the model emitted no COMMAND:/SCRIPT: but the
                # entire response is a single non-empty line, treat it as the
                # command. This handles models that occasionally drop the keyword
                # prefix. Prose responses spanning multiple lines are ignored.
                candidate = thought_lines[-1].strip()
                if candidate and len([l for l in thought_lines if l.strip()]) == 1:
                    command_line = candidate

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

    def _handle_script_line(self, line: str) -> None:
        """
        Parse a SCRIPT: directive and populate the script queue.

        Called from _llm_cycle when the LLM emits a SCRIPT: line. Each
        pipe-delimited step is queued for sequential dispatch by _drain_script
        without further LLM involvement.
        """
        m = _SCRIPT_RE.match(line)
        if not m:
            return
        steps = [s.strip().strip("`") for s in m.group(1).split("|") if s.strip()]
        if steps:
            n = len(steps)
            self._script_queue = steps
            self._pending_done_msg = f"[Script] 0/{n} remaining."
            self._on_thought(f"[Script] Queued {n} commands.")

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
