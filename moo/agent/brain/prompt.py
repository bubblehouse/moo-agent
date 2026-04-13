"""
Pure string-construction helpers for LLM prompts.

``build_system_prompt(soul, tools_active)`` assembles the system prompt from
the soul's mission, persona, context, the directive-grammar instructions
(text-mode vs tool-mode variant), and optional addendum.

``build_user_message(memory_summary, current_goal, current_plan, plan_exhausted,
idle_wakeup_count, window_lines)`` constructs the user-turn message including
memory summary, goal/plan state, idle-wakeup counter, and the rolling output
window.

Both functions are pure — no Brain state, no I/O. Brain calls them with values
pulled from its own session state.
"""

from typing import Iterable

from moo.agent.soul import Soul


PATCH_INSTRUCTIONS = """\
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


PATCH_INSTRUCTIONS_TOOLS_ACTIVE = """\
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

Prefer tool calls for actions that have a matching tool. For MOO commands that
have NO matching tool (e.g. `@realm $room`, `@eval`, `@tunnel`, `@recycle`),
use a SCRIPT: line directly:
SCRIPT: @realm $room
SCRIPT: @eval "print('hello')"
These are valid even in tool mode — they execute the raw MOO command."""


SUMMARIZE_SYSTEM = (
    "Summarize the following MOO game session log in 2-3 concise sentences. "
    "Be specific: include locations visited, objects found or used, and notable events."
)


def build_system_prompt(soul: Soul, tools_active: bool) -> str:
    """Assemble the system prompt for an LLM cycle.

    When ``tools_active`` is True the tool-mode directive preamble is used
    (the tool schemas carry the action vocabulary, so only meta-directives
    are included). Otherwise the full text-mode grammar is emitted.
    """
    parts = [soul.mission, soul.persona]
    if soul.context:
        parts.append(soul.context)
    parts.append(PATCH_INSTRUCTIONS_TOOLS_ACTIVE if tools_active else PATCH_INSTRUCTIONS)
    if soul.addendum:
        parts.append(soul.addendum)
    return "\n\n".join(parts)


def build_user_message(
    memory_summary: str,
    current_goal: str,
    current_plan: list[str],
    plan_exhausted: bool,
    idle_wakeup_count: int,
    window_lines: Iterable[str],
) -> str:
    """Construct the user-turn message, including memory and planning state."""
    parts: list[str] = []
    if memory_summary:
        parts.append(f"[Earlier context: {memory_summary}]")
    if current_goal:
        parts.append(f"Current goal: {current_goal}")
    if current_plan:
        parts.append(f"Remaining plan: {' | '.join(current_plan)}")
    elif plan_exhausted:
        parts.append("All planned rooms are built. Follow your Token Protocol: page your successor, then call done().")
    if idle_wakeup_count > 0:
        parts.append(f"[Idle wakeups since last server output: {idle_wakeup_count}]")
    parts.append("\n".join(window_lines))
    parts.append("\nWhat should you do next?")
    return "\n".join(parts)
