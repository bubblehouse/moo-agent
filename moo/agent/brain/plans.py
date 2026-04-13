"""
Plan persistence helpers: traversal plan and build plan YAML I/O.

Four free functions moved out of ``Brain`` so plan save/load logic can be
unit-tested against a plain ``BrainState`` and a ``tmp_path`` directory. All
functions take the same three context arguments:

- ``config_dir``: the agent's config directory, or ``None`` when the agent
  was constructed without one (smoke tests). In that case the helpers no-op.
- ``state``: the ``BrainState`` to read/mutate.
- ``on_thought``: callback used to surface persistence errors or diagnostic
  notices to the agent's thought log.

``save_build_plan`` additionally takes the raw ``content`` string from the
LLM's ``BUILD_PLAN:`` directive — it handles duplicate-plan rejection, YAML
write, room-name extraction, and the memory-summary override that keeps the
next LLM cycle focused on building rather than re-planning.
"""

import time
from pathlib import Path
from typing import Callable, Optional

from moo.agent.brain.directives import extract_room_names_from_yaml
from moo.agent.brain.state import BrainState


ThoughtCallback = Callable[[str], None]


def save_traversal_plan(config_dir: Optional[Path], state: BrainState, on_thought: ThoughtCallback) -> None:
    """Persist ``state.current_plan`` to ``builds/traversal_plan.txt``."""
    if not config_dir:
        return
    try:
        builds_dir = config_dir / "builds"
        builds_dir.mkdir(exist_ok=True)
        plan_path = builds_dir / "traversal_plan.txt"
        plan_path.write_text("\n".join(state.current_plan), encoding="utf-8")
    except OSError as e:
        on_thought(f"[Traversal Plan] Error saving: {e}")


def load_traversal_plan(config_dir: Optional[Path], state: BrainState, on_thought: ThoughtCallback) -> None:
    """
    On startup, restore ``state.current_plan`` from ``builds/traversal_plan.txt``.

    Called after ``load_latest_build_plan()`` — only runs if no build plan was
    found, so traversal agents (Tinker, Joiner, Harbinger) that don't emit
    ``BUILD_PLAN:`` can still resume their room list after a restart.
    """
    if not config_dir:
        return
    plan_path = config_dir / "builds" / "traversal_plan.txt"
    if not plan_path.exists():
        return
    try:
        entries = [l.strip() for l in plan_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    except OSError:
        return
    if entries:
        state.current_plan = entries
        state.plan_exhausted = False


def load_latest_build_plan(config_dir: Optional[Path], state: BrainState, on_thought: ThoughtCallback) -> None:
    """
    On startup, reload room names from the most recent build plan YAML.

    Populates ``state.current_plan`` so the agent doesn't re-plan from scratch
    after a restart. The agent's ``PLAN:`` directives will shrink the list as
    rooms are completed; if none have been emitted yet we load all rooms and
    let the agent skip already-built ones based on world state.
    """
    if not config_dir:
        return
    builds_dir = config_dir / "builds"
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
    room_names = extract_room_names_from_yaml(text)
    if room_names:
        state.current_plan = room_names
        state.plan_from_disk = True
        state.plan_exhausted = False


def save_build_plan(
    config_dir: Optional[Path],
    state: BrainState,
    on_thought: ThoughtCallback,
    content: str,
) -> None:
    """
    Write a build plan to ``builds/`` as a datestamped YAML file.

    Only the first ``BUILD_PLAN:`` per session is accepted. If
    ``state.current_plan`` is already populated (from a prior plan or from
    disk on startup), subsequent ``BUILD_PLAN:`` directives are logged as
    thoughts and ignored to prevent the agent from re-planning mid-session
    with a shorter room list.
    """
    # current_plan may contain room IDs (e.g. "#128") injected from an incoming
    # token page — those are visit-list context for worker agents, not an
    # active build plan. Allow BUILD_PLAN: to override them. A real build plan
    # contains room names (no leading "#").
    plan_has_only_ids = state.current_plan and all(r.startswith("#") for r in state.current_plan)
    if state.current_plan and not plan_has_only_ids and not state.plan_from_disk:
        on_thought(
            "[Build Plan] Ignored duplicate BUILD_PLAN: — plan already active "
            f"({len(state.current_plan)} rooms remaining). "
            "Do not emit BUILD_PLAN: again this session."
        )
        return
    if not config_dir:
        return
    builds_dir = config_dir / "builds"
    timestamp = time.strftime("%Y-%m-%d-%H-%M")
    plan_path = builds_dir / f"{timestamp}.yaml"
    expanded = content.replace("\\n", "\n")
    try:
        builds_dir.mkdir(exist_ok=True)
        plan_path.write_text(expanded + "\n", encoding="utf-8")
    except OSError as e:
        on_thought(f"[Build Plan] Error saving: {e}")
        return
    on_thought(f"[Build Plan] Saved to {plan_path.name}")
    # Extract top-level room names (2-space indent) — exclude nested object names.
    room_names = extract_room_names_from_yaml(expanded)
    if room_names:
        state.current_plan = room_names
        state.plan_from_disk = False
        state.plan_exhausted = False
    # Override memory summary so the next LLM cycle starts building instead of
    # re-planning. This survives the DONE: goal-clear that typically follows.
    room_list = " | ".join(room_names) if room_names else "the planned rooms"
    state.memory_summary = (
        "BUILD_PLAN has been saved. Do not emit BUILD_PLAN again. "
        f"Your rooms to build in order: {room_list}. "
        "Start executing the plan NOW: issue SCRIPT: or COMMAND: blocks "
        "with actual MOO commands (@dig, @describe, @create, go) to build "
        "the first room in the plan. Follow the plan exactly — "
        "do not invent new room names."
    )
