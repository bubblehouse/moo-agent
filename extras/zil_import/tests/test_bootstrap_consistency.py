"""
Bootstrap-consistency lint: walk generated verb output and assert
shebang/body alignment, iobj-host dispatch coverage, and resolvable
PERFORM targets.

Patterned after ``test_no_zmachine_leakage.py``: ratchets allowlist
entries down as bugs are fixed, runs on committed bootstrap output.
The HHG shakedown surfaced this exact bug class repeatedly
(``lie-down`` body vs ``lie_down`` shebang; ``--dspec this`` with no
``--ispec``; ``_.perform('block_with', …)`` against an unregistered
name). Catching them at test-collection time is much cheaper than
discovering them mid-puzzle.

Baseline lives in ``_consistency_baseline.json``. Regenerate with
``uv run python extras/zil_import/tests/_collect_consistency_baseline.py``
after intentional fixes.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from extras.zil_import.verb_metadata import (
    body_perform_targets,
    body_player_verb_literals,
    body_references_prsi,
    iter_verb_files,
)

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[2]
_BOOTSTRAP_ROOTS = {
    "zork1": _REPO_ROOT / "moo" / "bootstrap" / "zork1",
    "hhg": _REPO_ROOT / "moo" / "bootstrap" / "hhg",
}
_BASELINE_PATH = _HERE / "_consistency_baseline.json"


def _baseline() -> dict:
    if not _BASELINE_PATH.exists():
        return {}
    return json.loads(_BASELINE_PATH.read_text())


_BASELINE = _baseline()


def _bootstrap_params():
    """Yield (id, root) for every bootstrap dataset that exists on disk."""
    for name, root in _BOOTSTRAP_ROOTS.items():
        if root.is_dir():
            yield pytest.param(root, id=name)


@pytest.mark.parametrize("bootstrap_root", list(_bootstrap_params()))
def test_player_verb_alignment(bootstrap_root: Path) -> None:
    """
    Every ``the_player_verb == 'X'`` (or ``in [...]``) literal in a verb
    body must appear in the shebang's ``names`` list, otherwise the body
    has a branch the dispatcher never reaches.

    Per-file baseline allowlist in ``_consistency_baseline.json``
    captures known-pending violations (substrate handlers, daemons that
    branch on the player's last verb, room turnfuncs, etc.). New
    violations fail the test. Fixing a baseline entry must be paired
    with rerunning ``_collect_consistency_baseline.py`` to ratchet it
    out — pre-existing entries that disappear silently become coverage
    debt.
    """
    dataset = bootstrap_root.name
    baseline = _BASELINE.get(dataset, {}).get("player_verb_alignment", {})
    new_violations: list[str] = []
    healed: list[str] = []
    seen: set[str] = set()
    for path, shebang, body in iter_verb_files(bootstrap_root):
        rel = path.relative_to(bootstrap_root).as_posix()
        seen.add(rel)
        literals = body_player_verb_literals(body)
        unregistered = sorted(literals - set(shebang.names))
        if not unregistered:
            if rel in baseline:
                healed.append(rel)
            continue
        baseline_set = set(baseline.get(rel, []))
        new = sorted(set(unregistered) - baseline_set)
        if new:
            new_violations.append(f"{rel}: {new!r} (shebang registers {list(shebang.names)!r})")
    # Stale baseline entries — file no longer exists at all.
    for rel in baseline:
        if rel not in seen:
            healed.append(rel)
    msgs: list[str] = []
    if new_violations:
        msgs.append("NEW player-verb alignment violations:\n  " + "\n  ".join(new_violations))
    if healed:
        msgs.append(
            "BASELINE files no longer violating (ratchet down — rerun "
            "_collect_consistency_baseline.py):\n  " + "\n  ".join(sorted(healed))
        )
    if msgs:
        pytest.fail("\n".join(msgs))


@pytest.mark.parametrize("bootstrap_root", list(_bootstrap_params()))
def test_iobj_host_dispatch(bootstrap_root: Path) -> None:
    """
    Verb files whose body inspects PRSI must register an ``--ispec``
    so the parser routes prepositional sentences (``put X on Y``) to
    them. ``--dspec this`` with no ispec means PRSO-anchored dispatch
    only, and the body branch on PRSI never fires.

    Surfaced bug class: HHG hook/drain/satchel hangers; per-game
    instance handlers in Zork basket/dam/mirror/etc. that may or may
    not actually need ispec — the baseline captures the current set.
    """
    dataset = bootstrap_root.name
    baseline = set(_BASELINE.get(dataset, {}).get("iobj_host_dispatch", []))
    current: set[str] = set()
    for path, shebang, body in iter_verb_files(bootstrap_root):
        rel = path.relative_to(bootstrap_root).as_posix()
        if shebang.dspec != "this":
            continue
        if not body_references_prsi(body):
            continue
        if not shebang.ispec or not any(spec == "this" for spec in shebang.ispec.values()):
            current.add(rel)
    new_violations = sorted(current - baseline)
    healed = sorted(baseline - current)
    msgs: list[str] = []
    if new_violations:
        msgs.append(
            "NEW iobj-host dispatch violations (--dspec this + PRSI use, "
            "no --ispec PREP:this):\n  " + "\n  ".join(new_violations)
        )
    if healed:
        msgs.append(
            "BASELINE files no longer violating (ratchet down — rerun "
            "_collect_consistency_baseline.py):\n  " + "\n  ".join(healed)
        )
    if msgs:
        pytest.fail("\n".join(msgs))


@pytest.mark.parametrize("bootstrap_root", list(_bootstrap_params()))
def test_perform_targets_resolve(bootstrap_root: Path) -> None:
    """
    Every ``_.perform('X', …)`` or ``<obj>.perform('X', …)`` call must
    name a verb registered somewhere in the bootstrap output.

    Currently 0 violations on both datasets — earlier translator fixes
    closed the original ``BLOCK-WITH`` etc. gaps. Baseline is empty;
    any new violation fails the test outright.
    """
    dataset = bootstrap_root.name
    baseline_pairs = {tuple(p) for p in _BASELINE.get(dataset, {}).get("perform_targets", [])}
    registered: set[str] = set()
    for _path, shebang, _body in iter_verb_files(bootstrap_root):
        registered.update(shebang.names)
    current: set[tuple[str, str]] = set()
    locations: dict[tuple[str, str], int] = {}
    for path, _shebang, body in iter_verb_files(bootstrap_root):
        rel = path.relative_to(bootstrap_root).as_posix()
        for target, line in body_perform_targets(body):
            if target in registered:
                continue
            current.add((rel, target))
            locations.setdefault((rel, target), line)
    new_violations = sorted(current - baseline_pairs)
    healed = sorted(baseline_pairs - current)
    msgs: list[str] = []
    if new_violations:
        msgs.append(
            "NEW unresolved perform targets:\n  "
            + "\n  ".join(
                f"{rel}:{locations.get((rel, target), '?')}: _.perform({target!r}, …) — no verb registered"
                for rel, target in new_violations
            )
        )
    if healed:
        msgs.append(
            "BASELINE perform-targets no longer violating (ratchet down — "
            "rerun _collect_consistency_baseline.py):\n  " + "\n  ".join(f"{rel}: {target}" for rel, target in healed)
        )
    if msgs:
        pytest.fail("\n".join(msgs))
