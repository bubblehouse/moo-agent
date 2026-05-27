"""
Translator coverage baseline-ratchet test.

After each ``python -m moo.zil_import`` run, ``moo/bootstrap/<game>/coverage.json``
records every silently-dropped clause / rule / form the translator
emitted (see ``moo/zil_import/audit.py`` for the drop catalog).

This test compares the live coverage report against the baseline in
``_translator_coverage_baseline.json``.  Two failure modes:

- **New violation** — a routine grows a drop that isn't in the baseline.
  Surfaces a translator regression at test time, not mid-shakedown.
- **Healed violation** — a baseline drop no longer fires (translator
  improvement closed the gap).  The baseline must be re-collected via
  ``_collect_coverage_baseline.py`` so future regressions still trip
  the new-violation arm.

Mirrors the pattern in ``test_bootstrap_consistency.py`` —
``test_player_verb_alignment`` is the proven shape this borrows.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[2]
_BOOTSTRAP_ROOTS = {
    "zork1": _REPO_ROOT / "moo" / "bootstrap" / "zork1",
    "hhg": _REPO_ROOT / "moo" / "bootstrap" / "hhg",
}
_BASELINE_PATH = _HERE / "_translator_coverage_baseline.json"
_BASELINE = json.loads(_BASELINE_PATH.read_text()) if _BASELINE_PATH.exists() else {}


def _coverage_params():
    for dataset, root in _BOOTSTRAP_ROOTS.items():
        coverage = root / "coverage.json"
        if coverage.is_file():
            yield pytest.param(dataset, coverage, id=dataset)


def test_coverage_json_present() -> None:
    """
    Sentinel: every bootstrap dataset must have a fresh ``coverage.json``.

    Without this guard, ``test_translator_coverage_baseline`` is
    parametrized over an empty list and silently passes — the ratchet
    can't ratchet what it never reads.  A missing ``coverage.json`` means
    the regen step didn't run (or wrote elsewhere); re-run
    ``python -m moo.zil_import <game>.zil --output <root>`` to refresh.
    """
    missing = [
        str(root / "coverage.json")
        for dataset, root in _BOOTSTRAP_ROOTS.items()
        if not (root / "coverage.json").is_file()
    ]
    if missing:
        pytest.fail(
            "coverage.json missing for one or more datasets; rerun "
            "`python -m moo.zil_import <game>.zil --output <root>` to refresh:\n  " + "\n  ".join(missing)
        )


def _drop_key(drop: dict) -> tuple:
    """Hashable identity for a drop entry.  Equal drops compare equal."""
    return tuple(sorted((k, repr(v)) for k, v in drop.items()))


@pytest.mark.parametrize("dataset,coverage_path", list(_coverage_params()))
def test_translator_coverage_baseline(dataset: str, coverage_path: Path) -> None:
    """
    Live translator drops must match the baseline routine-by-routine.

    Drops aren't expected to *vanish* without explicit ratchet — that's
    coverage debt going the wrong direction (a translator fix that
    closed a gap should also remove the baseline entry).  Drops aren't
    expected to *appear* without explicit code change — that's a
    regression.
    """
    if dataset not in _BASELINE:
        pytest.fail(f"No baseline entry for {dataset!r}.  Rerun _collect_coverage_baseline.py to seed it.")
    baseline_drops = _BASELINE[dataset].get("drops", {})
    baseline_skipped = _BASELINE[dataset].get("skipped", {})
    live = json.loads(coverage_path.read_text())
    live_drops = {n: r["drops"] for n, r in live["routines"].items() if r.get("drops")}
    live_skipped = {n: r.get("reason", "") for n, r in live["routines"].items() if r.get("status") == "skipped"}

    new_violations: list[str] = []
    healed: list[str] = []
    skipped_diffs: list[str] = []

    seen_routines = set(baseline_drops) | set(live_drops)
    for routine in sorted(seen_routines):
        base = {_drop_key(d): d for d in baseline_drops.get(routine, [])}
        cur = {_drop_key(d): d for d in live_drops.get(routine, [])}
        new = sorted(cur.keys() - base.keys())
        gone = sorted(base.keys() - cur.keys())
        if new:
            new_violations.append(f"{routine}: NEW {[cur[k] for k in new]!r}")
        if gone:
            healed.append(f"{routine}: HEALED {[base[k] for k in gone]!r}")

    # Skipped routines (e.g. _SKIP_ROUTINES additions/removals) are
    # less critical but worth flagging — a routine moving in/out of
    # _SKIP_ROUTINES changes the dispatch surface.
    seen_skipped = set(baseline_skipped) | set(live_skipped)
    for routine in sorted(seen_skipped):
        if routine in baseline_skipped and routine not in live_skipped:
            skipped_diffs.append(f"{routine}: no longer skipped (was {baseline_skipped[routine]!r})")
        elif routine in live_skipped and routine not in baseline_skipped:
            skipped_diffs.append(f"{routine}: newly skipped ({live_skipped[routine]!r})")

    msgs: list[str] = []
    if new_violations:
        msgs.append("NEW translator drops:\n  " + "\n  ".join(new_violations))
    if healed:
        msgs.append(
            "HEALED translator drops (rerun _collect_coverage_baseline.py to ratchet):\n  " + "\n  ".join(healed)
        )
    if skipped_diffs:
        msgs.append("Skipped-routine diffs:\n  " + "\n  ".join(skipped_diffs))
    if msgs:
        pytest.fail("\n\n".join(msgs))
