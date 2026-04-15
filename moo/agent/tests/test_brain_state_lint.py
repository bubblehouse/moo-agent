"""
Lint check: assert the Step 6 BrainState rename left no stragglers.

Every session field lives on ``Brain._state`` now. Any remaining
``self._<field>`` or ``brain._<field>`` reference inside ``moo/agent/`` (aside
from brain/state.py itself, which defines the names) would silently create
a stray attribute instead of mutating session state. This test grep-walks
the package to catch forgotten renames.
"""

import re
from pathlib import Path

_FIELDS = (
    "current_goal",
    "current_plan",
    "memory_summary",
    "pending_done_msg",
    "idle_wakeup_count",
    "plan_exhausted",
    "session_done",
    "foreman_paged",
    "plan_from_disk",
    "rooms_built",
    "goal_only_count",
    "token_dispatched_at",
    "token_dispatched_to",
    "prior_goal_for_reconnect",
)

_PATTERN = re.compile(r"\b(?:self|brain)\._(" + "|".join(_FIELDS) + r")\b")

_AGENT_DIR = Path(__file__).resolve().parent.parent


def test_no_stray_brain_state_references() -> None:
    offenders: list[str] = []
    for path in _AGENT_DIR.rglob("*.py"):
        # Skip brain/state.py itself — that's where the fields are defined.
        if path.name == "state.py" and path.parent.name == "brain":
            continue
        text = path.read_text()
        for i, line in enumerate(text.splitlines(), start=1):
            if _PATTERN.search(line):
                rel = path.relative_to(_AGENT_DIR.parent.parent)
                offenders.append(f"{rel}:{i}: {line.strip()}")
    assert not offenders, (
        "Stray BrainState field references found — all session state must go "
        "through self._state / brain._state:\n  " + "\n  ".join(offenders)
    )
