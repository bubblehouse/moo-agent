"""
Helper script — run by hand to regenerate the translator coverage baseline.

Reads ``moo/bootstrap/<game>/coverage.json`` produced by the most recent
``python -m moo.zil_import`` run for each game, distils it down to the
drop catalog the test ratchets against, and writes
``_translator_coverage_baseline.json``.

Run after intentional translator improvements to ratchet the allowlist
down — drops that disappear must be removed from the baseline so future
regressions surface as new violations.

    uv run python moo/zil_import/tests/_collect_coverage_baseline.py

This mirrors ``_collect_consistency_baseline.py`` in shape (same
new-violations + healed-violations pattern).
"""

from __future__ import annotations

import json
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[2]
_BOOTSTRAP_ROOTS = {
    "zork1": _REPO_ROOT / "moo" / "bootstrap" / "zork1",
    "hhg": _REPO_ROOT / "moo" / "bootstrap" / "hhg",
}
_OUT = _HERE / "_translator_coverage_baseline.json"


def _drop_key(drop: dict) -> tuple:
    """Stable identity tuple for a drop, used to compare baseline vs live."""
    return tuple(sorted(drop.items(), key=lambda kv: kv[0]))


def collect() -> None:
    baseline: dict[str, dict] = {}
    for dataset, root in _BOOTSTRAP_ROOTS.items():
        coverage_path = root / "coverage.json"
        if not coverage_path.is_file():
            print(f"  {dataset}: skipped (no {coverage_path})")
            continue
        data = json.loads(coverage_path.read_text())
        drops: dict[str, list[dict]] = {}
        skipped: dict[str, str] = {}
        for routine, rec in sorted(data["routines"].items()):
            if rec.get("status") == "skipped":
                skipped[routine] = rec.get("reason", "")
            if rec.get("drops"):
                drops[routine] = rec["drops"]
        baseline[dataset] = {
            "drops": drops,
            "skipped": skipped,
            "summary": data["summary"],
        }
    _OUT.write_text(json.dumps(baseline, indent=2, sort_keys=True) + "\n")
    print(f"Wrote {_OUT}")
    for dataset, d in baseline.items():
        print(
            f"  {dataset}: {sum(len(v) for v in d['drops'].values())} drops "
            f"across {len(d['drops'])} routines, "
            f"{len(d['skipped'])} skipped routines"
        )


if __name__ == "__main__":
    collect()
