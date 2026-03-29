"""
Brain: perception-action loop for moo-agent.

Receives server output via enqueue_output(), checks reflexive rules first, then
falls back to LLM inference. Supports append-only soul evolution via
SOUL_PATCH_RULE: / SOUL_PATCH_VERB: directives in LLM responses.

Does not import from moo.core or trigger Django setup.
"""

import asyncio
import collections
import os
import re
from pathlib import Path
from typing import Callable

from asynciolimiter import LeakyBucketLimiter
from anthropic import AsyncAnthropic

from moo.agent.soul import Soul, append_patch, compile_rules, parse_soul

_PATCH_RULE_RE = re.compile(r"^SOUL_PATCH_RULE:\s*(.+)$")
_PATCH_VERB_RE = re.compile(r"^SOUL_PATCH_VERB:\s*(.+)$")
_COMMAND_RE = re.compile(r"^COMMAND:\s*(.+)$")
_ARROW_RE = re.compile(r"\s*->\s*")

_PATCH_INSTRUCTIONS = """\
Respond with exactly one line prefixed COMMAND: containing the single MOO command
to execute next. Any reasoning or notes must appear on lines before it — they are
visible to you but never sent to the server.

Example:
I need to navigate to the library wing before creating the exit.
COMMAND: go north

You may also include soul patch proposals on their own lines before COMMAND::
SOUL_PATCH_RULE: ^You arrive -> look
SOUL_PATCH_VERB: check_exits -> @exits
COMMAND: go north

Only propose a patch when you have encountered the same situation multiple times
and a fixed response is clearly correct."""


class Brain:
    """
    Async perception-action loop.

    Wired to a MooConnection via enqueue_output() and send_command callbacks.
    Reflexive rules bypass the LLM for immediate dispatch. LLM inference uses
    a skip-on-busy semaphore so rapid output never queues multiple API calls.
    """

    def __init__(
        self,
        soul: Soul,
        config,
        send_command: Callable[[str], None],
        on_thought: Callable[[str], None],
        config_dir: Path | None = None,
    ):
        self._soul = soul
        self._config = config
        self._send_command = send_command
        self._on_thought = on_thought
        self._config_dir = config_dir

        self._output_queue: asyncio.Queue[str] = asyncio.Queue()
        self._window: collections.deque[str] = collections.deque(maxlen=config.agent.memory_window_lines)
        self._compiled_rules = compile_rules(soul)
        self._limiter = LeakyBucketLimiter(config.agent.command_rate_per_second)
        self._llm_sem = asyncio.Semaphore(1)

    def enqueue_output(self, text: str) -> None:
        """Called by the connection layer when server output arrives."""
        self._output_queue.put_nowait(text)

    def enqueue_instruction(self, text: str) -> None:
        """
        Called when the operator types an instruction in the TUI.

        The text is added to the rolling window as an operator message and an
        LLM cycle is forced immediately — rule matching is skipped because a
        direct instruction should always reach the LLM.
        """
        self._window.append(f"[Operator]: {text}")
        asyncio.get_event_loop().create_task(self._llm_cycle())

    async def run(self) -> None:
        """Main perception-action loop. Runs until cancelled."""
        while True:
            text = await self._output_queue.get()
            self._window.append(text)

            matched = self._check_rules(text)
            if matched:
                await self._dispatch(matched)
            else:
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

    async def _llm_cycle(self) -> None:
        """Single LLM inference cycle. Skips if another call is already in flight."""
        if self._llm_sem.locked():
            return
        async with self._llm_sem:
            api_key = os.environ.get(self._config.llm.api_key_env, "")
            client = AsyncAnthropic(api_key=api_key)

            prompt_parts = [self._soul.mission, self._soul.persona]
            if self._soul.context:
                prompt_parts.append(self._soul.context)
            prompt_parts.append(_PATCH_INSTRUCTIONS)
            system_prompt = "\n\n".join(prompt_parts)
            user_message = "\n".join(self._window) + "\n\nWhat should you do next?"

            try:
                resp = await client.messages.create(
                    model=self._config.llm.model,
                    max_tokens=512,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_message}],
                )
            except Exception:  # pylint: disable=broad-exception-caught
                return

            response_text = resp.content[0].text if resp.content else ""
            command_line = None
            thought_lines = []

            for line in response_text.splitlines():
                patch_rule = _PATCH_RULE_RE.match(line)
                patch_verb = _PATCH_VERB_RE.match(line)
                cmd_match = _COMMAND_RE.match(line)
                if patch_rule:
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
                return

            command = self._resolve_intent(command_line)
            await self._dispatch(command)

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
        self._send_command(command)
