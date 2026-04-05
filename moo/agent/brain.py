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
from anthropic import APIStatusError, AsyncAnthropic, AsyncAnthropicBedrock

from moo.agent.soul import Soul, append_patch, compile_rules, parse_soul
from moo.agent.tools import LLMResponse, ToolSpec, get_tool, parse_tool_line


class Status(enum.Enum):
    READY = "ready"  # idle, waiting for events
    SLEEPING = "sleeping"  # LLM call in flight or wakeup timer <30 s away
    THINKING = "thinking"  # actively processing an event


_PATCH_RULE_RE = re.compile(r"^SOUL_PATCH_RULE:\s*(.+)$")
_PATCH_VERB_RE = re.compile(r"^SOUL_PATCH_VERB:\s*(.+)$")
_PATCH_NOTE_RE = re.compile(r"^SOUL_PATCH_NOTE:\s*(.+)$")
_BUILD_PLAN_RE = re.compile(r"^BUILD_PLAN:\s*(.+)$")
_COMMAND_RE = re.compile(r"^COMMAND:\s*(.+)$")
_SCRIPT_RE = re.compile(r"^SCRIPT:\s*(.+)$")
_DONE_RE = re.compile(r"^DONE:\s*(.+)$")
_GOAL_RE = re.compile(r"^GOAL:\s*(.+)$")
_PLAN_RE = re.compile(r"^PLAN:\s*(.+)$")
_ARROW_RE = re.compile(r"\s*->\s*")
_DIG_SUCCESS_RE = re.compile(r'^Dug an exit \w+ to "([^"]+)"\.')

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

Use SOUL_PATCH_NOTE to record a fact you discovered through trial and error —
something that would have prevented a mistake if you had known it up front.
Notes are stored and included in future sessions. Emit one as soon as you
self-correct, not after multiple repetitions:
SOUL_PATCH_NOTE: obj.name is a model field — always call obj.save() after assigning it

Use SOUL_PATCH_RULE or SOUL_PATCH_VERB only when you have encountered the same
situation multiple times and a fixed response is clearly correct.

Emit BUILD_PLAN: before starting a new construction phase. Use \\n for newlines
inside the plan — they are expanded to real newlines when the file is written.
The plan is saved to builds/YYYY-MM-DD-HH-MM.yaml next to the logs folder:
BUILD_PLAN: phase: "The East Wing"\\nrooms:\\n  - The Acid Bath\\n  - The Caustic Vault\\nobjects:\\n  - acid bath\\n  - drum rack\\nverbs:\\n  - pour\\nnpcs: []"""

_PATCH_INSTRUCTIONS_TOOLS_ACTIVE = """\
Use the provided tools to act. Each tool call translates to one or more MOO
commands executed in order. You may call multiple tools in a single response
to batch a sequence of actions (e.g. dig + go + describe).

Always emit a GOAL: line so your current objective is visible:
GOAL: <one-line objective>

When a goal is fully complete, call the done() tool with a summary.

You may still emit SOUL_PATCH_* and BUILD_PLAN: directives in plain text:
SOUL_PATCH_RULE: ^You arrive -> look
SOUL_PATCH_NOTE: obj.name is a model field — always call obj.save() after assigning it
BUILD_PLAN: phase: "The East Wing"\\nrooms:\\n  - The Acid Bath\\nobjects:\\n  - drum rack\\nverbs:\\n  - pour\\nnpcs: []

DO NOT emit COMMAND: or SCRIPT: when tools are available — use tool calls instead."""

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
    "There is no ",
    "I don't understand",
    "You can't",
    "That doesn't",
    "Huh?",
    "There is already an exit",
    "An error occurred",
    "When you say,",
    "<|",  # Gemma special tokens leaking into commands (e.g. <|tool_response>)
    "Go where?",  # tried to go a direction with no exit
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
        self._status = Status.READY
        self._last_activity = time.monotonic()
        self._script_queue: list[str] = []
        self._pending_done_msg: str = ""

        # Persistent planning state — carried forward in every LLM call
        self._current_goal: str = prior_goal
        self._current_plan: list[str] = []
        self._plan_exhausted: bool = False  # True after a plan is fully built
        self._memory_summary: str = prior_session_summary

        # Reload the most recent build plan on startup so the agent doesn't
        # re-plan from scratch after a restart.
        self._load_latest_build_plan()

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
        elif self._plan_exhausted:
            parts.append("All planned rooms are built. Emit DONE: to end the session.")
        parts.append("\n".join(self._window))
        parts.append("\nWhat should you do next?")
        return "\n".join(parts)

    async def run(self) -> None:
        """Main perception-action loop. Runs until cancelled."""
        asyncio.create_task(self._wakeup_loop())
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
                elif pending_llm:
                    pending_llm = False
                    if not (self._plan_exhausted and not self._current_goal):
                        asyncio.create_task(self._llm_cycle())
                continue

            self._set_status(Status.THINKING)
            self._window.append(text)

            # Auto-advance plan: when a @dig succeeds, remove the dug room and
            # all preceding rooms from _current_plan (they were already built).
            dig_match = _DIG_SUCCESS_RE.match(text)
            if dig_match and self._current_plan:
                dug_name = dig_match.group(1).strip()
                lower_names = [r.lower() for r in self._current_plan]
                try:
                    idx = lower_names.index(dug_name.lower())
                    self._current_plan = self._current_plan[idx + 1 :]
                    self._on_thought(f"[Plan] Advanced past {dug_name!r} — {len(self._current_plan)} rooms remaining.")
                    if not self._current_plan:
                        self._plan_exhausted = True
                        self._memory_summary = (
                            "BUILD_PLAN fully executed — all rooms are built. "
                            "Do not dig any more rooms. Emit DONE: now."
                        )
                        self._on_thought("[Plan] All planned rooms built. Emit DONE: now.")
                except ValueError:
                    pass  # dug room not in plan (improvised room) — ignore

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
                # Don't fire idle wakeups after the plan is done — the agent
                # has nothing left to do and would just invent extra work.
                if not (self._plan_exhausted and not self._current_goal):
                    asyncio.create_task(self._llm_cycle())

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

    async def _call_llm(self, client, system: str, user_message: str, max_tokens: int) -> LLMResponse:
        """
        Make one LLM inference call and return an LLMResponse.

        For Anthropic/Bedrock providers, native tool use is requested when
        self._tools is non-empty; tool_use content blocks are extracted into
        LLMResponse.tool_calls. For LM Studio, tool calls are parsed from
        TOOL: directives in the text response.
        """
        if self._config.llm.provider == "lm_studio":
            kwargs: dict = {}
            if self._tools:
                kwargs["tools"] = [t.to_openai_schema() for t in self._tools]
                kwargs["tool_choice"] = "auto"
            resp = await client.chat.completions.create(
                model=self._config.llm.model,
                max_tokens=max_tokens,
                extra_body={
                    "enable_thinking": False,
                    "cache_type_k": "q8_0",
                    "cache_type_v": "q8_0",
                },
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_message},
                ],
                **kwargs,
            )
            msg = resp.choices[0].message
            text = msg.content or ""
            tool_calls: list[tuple[str, dict]] = []
            if self._tools and msg.tool_calls:
                import json  # pylint: disable=import-outside-toplevel

                for tc in msg.tool_calls:
                    try:
                        args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                    except Exception:  # pylint: disable=broad-exception-caught
                        args = {}
                    tool_calls.append((tc.function.name, args))
            elif self._tools and text:
                # Fallback: parse TOOL: directives from text
                for line in text.splitlines():
                    parsed = parse_tool_line(line)
                    if parsed:
                        tool_calls.append(parsed)
            return LLMResponse(text=text, tool_calls=tool_calls)

        # Anthropic / Bedrock path
        from anthropic import NOT_GIVEN  # pylint: disable=import-outside-toplevel

        tools_schema = [t.to_anthropic_schema() for t in self._tools] if self._tools else NOT_GIVEN
        resp = await client.messages.create(
            model=self._config.llm.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_message}],
            tools=tools_schema,
        )
        text_parts = [b.text for b in resp.content if b.type == "text"]
        tool_calls = [(b.name, b.input) for b in resp.content if b.type == "tool_use"]
        return LLMResponse(text=" ".join(text_parts), tool_calls=tool_calls)

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
            # When tools are active the tool schemas carry the action vocabulary;
            # only include the SOUL_PATCH_* / GOAL: / DONE: meta-directives so the
            # model can still update goals and propose soul patches via text.
            if self._tools:
                prompt_parts.append(_PATCH_INSTRUCTIONS_TOOLS_ACTIVE)
            else:
                prompt_parts.append(_PATCH_INSTRUCTIONS)
            if self._soul.addendum:
                prompt_parts.append(self._soul.addendum)
            system_prompt = "\n\n".join(prompt_parts)
            user_message = self._build_user_message()

            llm_resp = None
            for attempt in range(4):
                try:
                    llm_resp = await self._call_llm(
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
            if llm_resp is None:
                self._set_status(Status.READY)
                return

            command_line = None
            thought_lines = []

            # Parse text portion — GOAL:, SOUL_PATCH_*, BUILD_PLAN:, DONE:,
            # and COMMAND:/SCRIPT: (fallback when no tools are configured).
            #
            # BUILD_PLAN: may be followed by multi-line YAML (real newlines, not
            # \n escapes). We accumulate lines until the next top-level directive.
            in_build_plan = False
            build_plan_lines: list[str] = []

            def _flush_build_plan() -> None:
                nonlocal in_build_plan, build_plan_lines
                if in_build_plan and build_plan_lines:
                    self._save_build_plan("\n".join(build_plan_lines))
                in_build_plan = False
                build_plan_lines = []

            for line in llm_resp.text.splitlines():
                # Strip markdown bold markers that some models emit around keywords
                # (e.g. "**COMMAND:** go north" → "COMMAND: go north")
                line = re.sub(r"^\*+\s*([A-Z_]+:)\s*\*+\s*", r"\1 ", line)
                patch_rule = _PATCH_RULE_RE.match(line)
                patch_verb = _PATCH_VERB_RE.match(line)
                patch_note = _PATCH_NOTE_RE.match(line)
                build_plan = _BUILD_PLAN_RE.match(line)
                cmd_match = _COMMAND_RE.match(line)
                script_match = _SCRIPT_RE.match(line)
                done_match = _DONE_RE.match(line)
                goal_match = _GOAL_RE.match(line)
                plan_match = _PLAN_RE.match(line)

                # If a new top-level directive appears, flush any pending BUILD_PLAN.
                is_directive = any(
                    [
                        goal_match,
                        plan_match,
                        patch_rule,
                        patch_verb,
                        patch_note,
                        build_plan,
                        cmd_match,
                        script_match,
                        done_match,
                    ]
                )
                if in_build_plan and is_directive:
                    _flush_build_plan()

                if in_build_plan:
                    build_plan_lines.append(line)
                    continue

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
                elif patch_note:
                    self._apply_patch("note", patch_note.group(1))
                elif build_plan:
                    first_line = build_plan.group(1).strip()
                    build_plan_lines = [first_line] if first_line else []
                    in_build_plan = True
                elif script_match:
                    self._handle_script_line(line)
                elif done_match:
                    self._pending_done_msg = done_match.group(1).strip()
                    self._current_goal = ""
                elif cmd_match:
                    command_line = cmd_match.group(1).strip().strip("`")
                else:
                    thought_lines.append(line)

            _flush_build_plan()  # flush if BUILD_PLAN was the last block in the response

            # Process structured tool calls from the LLM.
            # Each call is translated to MOO commands and appended to the script
            # queue in order. The 'done' tool updates goal state with no command.
            # Deduplicate: some models (Gemma 4) repeat the same call list twice
            # in one response. Remove consecutive exact duplicates to prevent
            # double-execution without dropping intentional repetitions.
            if llm_resp.tool_calls:
                seen: list[tuple[str, str]] = []
                deduped: list[tuple[str, dict]] = []
                for call in llm_resp.tool_calls:
                    key = (call[0], str(call[1]))
                    if key not in seen:
                        seen.append(key)
                        deduped.append(call)
                llm_resp = LLMResponse(text=llm_resp.text, tool_calls=deduped)
            if llm_resp.tool_calls:
                queued: list[str] = []
                for tool_name, tool_args in llm_resp.tool_calls:
                    spec = get_tool(self._tools, tool_name)
                    if spec is None:
                        self._on_thought(f"[Tool] Unknown tool '{tool_name}' — skipping.")
                        continue
                    if tool_name == "done":
                        summary = tool_args.get("summary", "").strip()
                        self._pending_done_msg = summary
                        self._current_goal = ""
                        if summary:
                            self._on_thought(f"[Done] {summary}")
                        continue
                    commands = spec.translate(tool_args)
                    queued.extend(commands)
                    self._on_thought(f"[Tool] {tool_name}({tool_args})")
                if queued:
                    self._script_queue = queued + self._script_queue

            thought = "\n".join(thought_lines).strip()
            if thought:
                self._on_thought(thought)

            # If a script was queued and no explicit COMMAND: was given, kick off
            # the first step immediately. Remaining steps are drained by run() as
            # server output arrives.
            if self._script_queue and not command_line:
                command_line = self._script_queue.pop(0)
            elif not command_line and thought_lines:
                # Fallback: if the model emitted no COMMAND:/SCRIPT:/tool calls but
                # the entire response is a single non-empty line, treat it as the
                # command. This handles models that occasionally drop the keyword
                # prefix. Prose responses spanning multiple lines are ignored.
                # Never dispatch bare directive keywords (GOAL, PLAN, DONE, SCRIPT,
                # COMMAND, TOOL) — these are malformed directives, not MOO commands.
                _BARE_DIRECTIVES = {"GOAL", "PLAN", "DONE", "SCRIPT", "COMMAND", "TOOL"}
                candidate = thought_lines[-1].strip()
                if (
                    candidate
                    and len([l for l in thought_lines if l.strip()]) == 1
                    and candidate.upper() not in _BARE_DIRECTIVES
                ):
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
        if entry_type == "note":
            note = directive.strip()
            if note and self._config_dir:
                append_patch(self._config_dir, "note", note, "")
        else:
            parts = _ARROW_RE.split(directive, maxsplit=1)
            if len(parts) != 2:
                return
            pattern_or_intent, command = parts[0].strip(), parts[1].strip()
            if not pattern_or_intent or not command:
                return
            if not self._config_dir:
                return
            append_patch(self._config_dir, entry_type, pattern_or_intent, command)

        if self._config_dir:
            # Reload the operational layer and recompile
            try:
                updated = parse_soul(self._config_dir)
                self._soul.rules = updated.rules
                self._soul.verb_mappings = updated.verb_mappings
                self._soul.context = updated.context
                self._compiled_rules = compile_rules(self._soul)
            except Exception:  # pylint: disable=broad-exception-caught
                pass

    def _load_latest_build_plan(self) -> None:
        """
        On startup, reload room names from the most recent build plan YAML.

        Populates _current_plan so the agent doesn't re-plan from scratch after
        a restart. The agent's PLAN: directives will shrink the list as rooms
        are completed; if none have been emitted yet we load all rooms and let
        the agent skip already-built ones based on world state.
        """
        if not self._config_dir:
            return
        builds_dir = self._config_dir / "builds"
        if not builds_dir.is_dir():
            return
        plan_files = sorted(builds_dir.glob("*.yaml"))
        if not plan_files:
            return
        latest = plan_files[-1]
        try:
            text = latest.read_text(encoding="utf-8")
        except OSError:
            return
        room_names = re.findall(
            r"^  - name:\s*[\"']?([^\"'\n]+)[\"']?",
            text,
            re.MULTILINE,
        )
        if room_names:
            self._current_plan = room_names
            self._plan_exhausted = False

    def _save_build_plan(self, content: str) -> None:
        """
        Write a build plan to builds/ as a datestamped YAML file.

        Only the first BUILD_PLAN: per session is accepted. If _current_plan is
        already populated (from a prior plan or from disk on startup), subsequent
        BUILD_PLAN: directives are logged as thoughts and ignored to prevent the
        agent from re-planning mid-session with a shorter room list.
        """
        if self._current_plan:
            self._on_thought(
                "[Build Plan] Ignored duplicate BUILD_PLAN: — plan already active "
                f"({len(self._current_plan)} rooms remaining). "
                "Do not emit BUILD_PLAN: again this session."
            )
            return
        if not self._config_dir:
            return
        builds_dir = self._config_dir / "builds"
        builds_dir.mkdir(exist_ok=True)
        timestamp = time.strftime("%Y-%m-%d-%H-%M")
        plan_path = builds_dir / f"{timestamp}.yaml"
        expanded = content.replace("\\n", "\n")
        plan_path.write_text(expanded + "\n", encoding="utf-8")
        self._on_thought(f"[Build Plan] Saved to {plan_path.name}")
        # Extract top-level room names (2-space indent) — exclude nested object names.
        room_names = re.findall(
            r"^  - name:\s*[\"']?([^\"'\n]+)[\"']?",
            expanded,
            re.MULTILINE,
        )
        if room_names:
            self._current_plan = room_names
            self._plan_exhausted = False
        # Override memory summary so the next LLM cycle starts building instead
        # of re-planning. This survives the DONE: goal-clear that typically follows.
        room_list = " | ".join(room_names) if room_names else "the planned rooms"
        self._memory_summary = (
            "BUILD_PLAN has been saved. Do not emit BUILD_PLAN again. "
            f"Your rooms to build in order: {room_list}. "
            "Start executing the plan NOW: issue SCRIPT: or COMMAND: blocks "
            "with actual MOO commands (@dig, @describe, @create, go) to build "
            "the first room in the plan. Follow the plan exactly — "
            "do not invent new room names."
        )

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
            steps.append(step)
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
