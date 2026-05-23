"""
Plan persistence helpers — traversal plan and build plan YAML I/O. See
``docs/source/explanation/agent-internals.md`` (Plan Persistence).

All functions accept ``config_dir`` (None → no-op), ``state``, and an
``on_thought`` callback for diagnostic output.
"""

import calendar
import json
import re
import time
from pathlib import Path
from typing import Callable, Optional

from moo.agent.brain.state import BrainState


ThoughtCallback = Callable[[str], None]

_ROOM_NAME_RE = re.compile(r"^  - name:\s*[\"']?([^\"'\n]+)[\"']?", re.MULTILINE)


def extract_room_names_from_yaml(text: str) -> list[str]:
    """Extract top-level room names (2-space indent) from a build plan YAML string."""
    return _ROOM_NAME_RE.findall(text)


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
    """Restore ``state.current_plan`` from ``builds/traversal_plan.txt``."""
    if not config_dir:
        return
    plan_path = config_dir / "builds" / "traversal_plan.txt"
    if not plan_path.exists():
        return
    try:
        entries = [line.strip() for line in plan_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except OSError:
        return
    if entries:
        state.current_plan = entries
        state.plan_exhausted = False


def load_latest_build_plan(config_dir: Optional[Path], state: BrainState, on_thought: ThoughtCallback) -> None:
    """Reload room names from the most recent ``builds/*.yaml`` build plan."""
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
    Write a build plan to ``builds/YYYY-MM-DD-HH-MM.yaml``. Only the first
    ``BUILD_PLAN:`` per session is accepted. See agent-internals: Build
    plans (Mason).
    """
    # Plans of only #IDs come from a token page (visit-list); a real build
    # plan has room names. Let BUILD_PLAN: override visit-list context.
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
    # 2-space indent only — excludes nested object names.
    room_names = extract_room_names_from_yaml(expanded)
    if room_names:
        state.current_plan = room_names
        state.plan_from_disk = False
        state.plan_exhausted = False
    # The summary override survives the DONE: goal-clear that typically follows.
    room_list = " | ".join(room_names) if room_names else "the planned rooms"
    state.memory_summary = (
        "BUILD_PLAN has been saved. Do not emit BUILD_PLAN again. "
        f"Your rooms to build in order: {room_list}. "
        "Start executing the plan NOW: issue SCRIPT: or COMMAND: blocks "
        "with actual MOO commands (@dig, @describe, @create, go) to build "
        "the first room in the plan. Follow the plan exactly — "
        "do not invent new room names."
    )


# ---------------------------------------------------------------------------
# Foreman token-dispatch state persistence
# ---------------------------------------------------------------------------
#
# Without this, restarting Foreman mid-chain (e.g. to pick up a code fix while
# Tinker held the token) wipes ``token_dispatched_to`` and ``..._at``. Foreman
# boots fresh, sees no dispatch state, auto-pages the first chain agent —
# trampling whoever actually had the token. The actor that *did* hold the
# token never gets the followup, and the worker that gets re-paged resets its
# session and starts over. We saw this drop the chain for 9 hours overnight.

_DISPATCH_STATE_FILE = "dispatch.json"
_DISPATCH_STATE_MAX_AGE_SECONDS = 600  # 10 min — older than this is stale, ignore


def save_dispatch_state(config_dir: Optional[Path], state: BrainState, on_thought: ThoughtCallback) -> None:
    """Persist Foreman's current token-dispatch target to ``dispatch.json``."""
    if not config_dir or not state.token_dispatched_to:
        return
    try:
        path = config_dir / _DISPATCH_STATE_FILE
        data = {
            "token_dispatched_to": state.token_dispatched_to,
            "dispatched_at_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        path.write_text(json.dumps(data), encoding="utf-8")
    except OSError as e:
        on_thought(f"[Dispatch] Error saving: {e}")


def clear_dispatch_state(config_dir: Optional[Path]) -> None:
    """Remove the persisted dispatch state file (used when a chain pass ends)."""
    if not config_dir:
        return
    path = config_dir / _DISPATCH_STATE_FILE
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def load_dispatch_state(config_dir: Optional[Path], state: BrainState, on_thought: ThoughtCallback) -> None:
    """Restore ``token_dispatched_to`` / ``token_dispatched_at`` if recent."""
    if not config_dir:
        return
    path = config_dir / _DISPATCH_STATE_FILE
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    iso = data.get("dispatched_at_iso") or ""
    try:
        # calendar.timegm treats the parsed struct as UTC (matches our gmtime
        # write side); time.mktime would re-interpret it as local time and
        # silently break under non-UTC timezones, especially during DST.
        dispatched_utc = calendar.timegm(time.strptime(iso, "%Y-%m-%dT%H:%M:%SZ"))
    except ValueError:
        return
    age = time.time() - dispatched_utc
    if age < 0 or age > _DISPATCH_STATE_MAX_AGE_SECONDS:
        on_thought(f"[Dispatch] Discarded stale dispatch state (age={age:.0f}s).")
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        return
    target = data.get("token_dispatched_to")
    if not target:
        return
    # token_dispatched_at uses monotonic time, which resets across restarts.
    # Set it to monotonic-now so the stall timer fires after the normal
    # interval — better than racing toward an instant stall-page.
    state.token_dispatched_to = target
    state.token_dispatched_at = time.monotonic()
    on_thought(f"[Dispatch] Restored — token currently with {target} (age={age:.0f}s).")
