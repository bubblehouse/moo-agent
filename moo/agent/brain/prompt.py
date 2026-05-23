"""
Pure prompt builders. ``build_system_prompt`` assembles the system message
(soul + structured-response format). ``build_user_message`` assembles the user
turn (memory summary + goal/plan + rolling window). Neither touches Brain state.

Stage-2: tools are registered on the PydanticAI Agent, which renders their
schemas to the model directly. The system prompt no longer carries a tool
reference block, and the ``actions`` paragraph in ``RESPONSE_FORMAT`` was
replaced with one sentence describing the tool-call channel.
"""

from typing import Iterable

from moo.agent.soul import Soul


RESPONSE_FORMAT = """\
You drive the MOO by calling tools and returning one structured response each
turn. The response has these meta-state fields:

- reasoning: brief private thinking. Visible to you, never sent to the server.
- goal: your one-line current objective. Always set it.
- done: when the goal is fully complete, set this to a one-line summary;
  otherwise leave it null.
- soul_patches: optional learned-knowledge entries (see below).
- build_plan: optional YAML build plan for a new construction phase.

Call tools as you need to act on the world. After each tool result you see,
decide the next call. Tool calls run inside one cycle — call ``dig`` then
``go`` then ``describe`` in sequence and you see each result before the next
call. When the goal is fully done, set ``done`` and return.

The ``respond`` tool is a last resort, for the rare turn when there is
genuinely nothing in the environment to act on. It is never for narrating a
decision. If you have worked out what to do, call the action tool now — do not
``respond`` to describe your plan and then stop.

After ``dig``, follow with ``go`` to enter the new room.

If a server_error tells you ``There is no '#N' here`` after a ``create``, DO
NOT substitute a different ``#N`` and retry. Either the object was made under
a different ID, or it wasn't made at all. Re-survey the room
(``survey(target="here")``) and read the actual ``#N`` from the ``Contents:``
block before retrying.

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


def build_system_prompt(soul: Soul) -> str:
    """Assemble the system prompt: soul + response format."""
    parts = [soul.mission, soul.persona]
    if soul.context:
        parts.append(soul.context)
    parts.append(RESPONSE_FORMAT)
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
