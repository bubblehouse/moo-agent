"""
Helper script — run by hand to regenerate the consistency baseline.

Walks both bootstrap datasets and writes the current set of violations
to ``_consistency_baseline.json``. Run after intentional fixes to
ratchet the allowlist down.

    uv run python moo/zil_import/tests/_collect_consistency_baseline.py
"""

from __future__ import annotations

import json
from pathlib import Path

from moo.zil_import.verb_metadata import (
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
_OUT = _HERE / "_consistency_baseline.json"


def collect():
    baseline: dict[str, dict] = {}
    for dataset, root in _BOOTSTRAP_ROOTS.items():
        if not root.is_dir():
            continue
        registered: set[str] = set()
        for _p, shebang, _b in iter_verb_files(root):
            registered.update(shebang.names)
        pva: dict[str, list[str]] = {}
        ihd: list[str] = []
        ptr: list[list[str]] = []
        for path, shebang, body in iter_verb_files(root):
            rel = path.relative_to(root).as_posix()
            literals = body_player_verb_literals(body)
            unregistered = sorted(literals - set(shebang.names))
            if unregistered:
                pva[rel] = unregistered
            if (
                shebang.dspec == "this"
                and body_references_prsi(body)
                and (not shebang.ispec or not any(spec == "this" for spec in shebang.ispec.values()))
            ):
                ihd.append(rel)
            for target, _line in body_perform_targets(body):
                if target not in registered:
                    ptr.append([rel, target])
        baseline[dataset] = {
            "player_verb_alignment": pva,
            "iobj_host_dispatch": sorted(ihd),
            "perform_targets": sorted(ptr),
        }
    _OUT.write_text(json.dumps(baseline, indent=2, sort_keys=True) + "\n")
    print(f"Wrote {_OUT}")
    for dataset, d in baseline.items():
        print(
            f"  {dataset}: {len(d['player_verb_alignment'])} alignment, "
            f"{len(d['iobj_host_dispatch'])} iobj, "
            f"{len(d['perform_targets'])} perform"
        )


if __name__ == "__main__":
    collect()
