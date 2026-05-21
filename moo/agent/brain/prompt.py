"""
Pure prompt builders. ``build_system_prompt`` assembles the system message
(soul + structured-response format + tool reference). ``build_user_message``
assembles the user turn (memory summary + goal/plan + rolling window). Neither
touches Brain state.
"""

from typing import Iterable

from moo.agent.soul import Soul
from moo.agent.tools import ToolSpec


RESPONSE_FORMAT = """\
You drive the MOO by returning one structured response each turn. The response
has these fields:

- reasoning: brief private thinking. Visible to you, never sent to the server.
- goal: your one-line current objective. Always set it.
- actions: an ordered list of tool calls to run this turn. Batch every step of
  a task into one list — never split a build across turns.
- done: when the goal is fully complete, set this to a one-line summary;
  otherwise leave it null.
- soul_patches: optional learned-knowledge entries (see below).
- build_plan: optional YAML build plan for a new construction phase.

Each action is an object: {"tool": "<name>", "args": {<string keys/values>}}.

Example — build and enter a room in one turn:
  goal: "build and enter the library"
  actions:
    {"tool": "dig", "args": {"direction": "north", "room_name": "The Library"}}
    {"tool": "go", "args": {"direction": "north"}}
    {"tool": "describe", "args": {"target": "here", "text": "Tall shelves."}}

Example — nothing to act on this turn:
  goal: "wait for the token"
  actions:
    {"tool": "respond", "args": {"message": "Idle until paged."}}

Use the respond tool when you have an observation but no environment action —
commentary is itself a tool call, never loose prose.

After dig(), always follow with go() in the same actions list — dig() creates
an exit but does not move you.

When you create an object, refer to it afterwards by its quoted name, never by
a #N placeholder you have not seen the server assign.

soul_patches entries each have a kind and content:
- kind "note": a fact you discovered by trial and error, e.g. "obj.name is a
  model field — call obj.save() after assigning it". Emit one as soon as you
  self-correct, not after repeating the mistake.
- kind "rule": a fixed "pattern -> command" reflex — only after seeing the
  same situation several times.
- kind "verb": an "intent -> @verb" mapping — same threshold as rule."""


SUMMARIZE_SYSTEM = (
    "Summarize the following MOO game session log in 2-3 concise sentences. "
    "Be specific: include locations visited, objects found or used, and notable events."
)


def render_tools(tools: list[ToolSpec]) -> str:
    """Render the available tools as a reference block for the system prompt."""
    lines = ["Available tools — use these names in the actions list:"]
    for spec in tools:
        params = ", ".join(p.name if p.required else f"{p.name}?" for p in spec.params)
        lines.append(f"- {spec.name}({params}): {spec.description}")
    return "\n".join(lines)


def build_system_prompt(soul: Soul, tools: list[ToolSpec]) -> str:
    """Assemble the system prompt: soul, response format, and tool reference."""
    parts = [soul.mission, soul.persona]
    if soul.context:
        parts.append(soul.context)
    parts.append(RESPONSE_FORMAT)
    if tools:
        parts.append(render_tools(tools))
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
