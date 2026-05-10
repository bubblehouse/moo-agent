"""
Regression test: Z-machine primitive leakage in generated zork1 bootstrap.

The translator currently leaves Z-machine names (``getpt``, ``ptsize``,
``UEXIT`` family, ``P-LEXV``, ``P-PRSO``, ``P-PRSI``, M-* lifecycle
constants) in generated code.  Some are dead at runtime (``getpt`` /
``ptsize`` have no Python definition); others are zstate keys that
recreate Z-machine globals on top of DjangoMOO's parser.

This test snapshots the current set of *files* that contain primitives.
If a primitive appears in a file that's not in the allowlist, the test
fails — that's new leakage from a translator/template change.

When Phase 3 cleans up a leak site, remove it from the allowlist.  The
test will fail until it's removed (because the file no longer needs the
exemption), forcing the ratchet downward.

See ``extras/skills/zork-shakedown/references/open-gaps.md`` § "Structural
polish backlog" for the cleanup plan.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_BOOTSTRAP_DIR = Path(__file__).resolve().parents[3] / "moo" / "bootstrap" / "zork1" / "verbs"

# Z-machine primitive identifiers that should not appear in generated code
# once Phase 3 lands.  Word-boundary anchored so "uexit" inside an unrelated
# identifier doesn't match.
_PRIMITIVES = [
    "getpt",
    "ptsize",
    "UEXIT",
    "NEXIT",
    "FEXIT",
    "CEXIT",
    "DEXIT",
    "P-LEXV",
    "P-PRSO",
    "P-PRSI",
    "PRSA",
]

# M-clause lifecycle constants.  Tracked separately because they're string
# literals compared against an `rarg` argument, not Python identifiers.
# These leak more broadly (every M-* clause file) and need a different
# cleanup path (decompose god-verbs in Phase 3).
_M_CONSTANTS = ["M-BEG", "M-LOOK", "M-END", "M-ENTER", "M-LEAVE", "M-FLASH", "M-OBJDESC"]

_PRIMITIVE_RE = re.compile(r"\b(" + "|".join(re.escape(p) for p in _PRIMITIVES) + r")\b")
_M_RE = re.compile(r"\b(" + "|".join(re.escape(p) for p in _M_CONSTANTS) + r")\b")

# Files that are known to contain Z-machine primitives as of 2026-05-03.
# Each entry is the path relative to ``moo/bootstrap/zork1/verbs/``.  Phase 3
# work that cleans a file should remove it from this set; a CI failure will
# remind us when a file no longer needs the exemption.
_KNOWN_PRIMITIVE_LEAKS: set[str] = {
    # Three remaining live leak sites — each walks the Z-machine exit /
    # property table via getpt + ptsize, which DjangoMOO doesn't have.
    # Fixing them requires translator-level rewrites of GETPT for
    # P?GLOBAL / P?EXIT semantics; deferred from the F-series.
    "zork_thing/daemons/i_sword.py",
    "zork_thing/helpers/other_side.py",
    "zork_thing/substrate_pre/pre_fill.py",
    # system/dispatch.py mentions getpt/ptsize/UEXIT in a comment
    # explaining the quarantine — not actual leakage.  Allowlisted so the
    # word-boundary scan doesn't trip on the documentation.
    "system/dispatch.py",
}


def _iter_verb_files() -> list[Path]:
    if not _BOOTSTRAP_DIR.exists():
        pytest.skip(f"bootstrap not generated yet: {_BOOTSTRAP_DIR}")
    return sorted(p for p in _BOOTSTRAP_DIR.rglob("*.py") if "__pycache__" not in p.parts)


def _rel(path: Path) -> str:
    return str(path.relative_to(_BOOTSTRAP_DIR))


def test_no_new_zmachine_primitive_leakage() -> None:
    """No file outside the allowlist may reference Z-machine primitives."""
    new_leaks: dict[str, set[str]] = {}
    for path in _iter_verb_files():
        rel = _rel(path)
        if rel in _KNOWN_PRIMITIVE_LEAKS:
            continue
        text = path.read_text(encoding="utf-8")
        hits = set(_PRIMITIVE_RE.findall(text))
        if hits:
            new_leaks[rel] = hits

    if new_leaks:
        msg = ["New Z-machine primitive leakage in generated code:"]
        for rel, hits in sorted(new_leaks.items()):
            msg.append(f"  {rel}: {sorted(hits)}")
        msg.append("")
        msg.append(
            "Either fix the translator/template to drop the primitive, or "
            "add the file to _KNOWN_PRIMITIVE_LEAKS in this test "
            "(only if you've documented the gap in extras/skills/"
            "zork-shakedown/references/open-gaps.md)."
        )
        pytest.fail("\n".join(msg))


def test_total_primitive_count_does_not_grow() -> None:
    """Aggregate primitive count across the bootstrap must not increase.

    A loose ratchet: the exact baseline is updated each time Phase 3 work
    reduces the count, so the test fails when a translator change causes
    leakage to grow even within the allowlisted files.

    Update the baseline when:
    - A translator/template change legitimately reduces the count → lower it
    - A new feature requires more primitives → raise it (and document why)
    """
    # Baseline as of 2026-05-03 after Phase 1+2 + Phase 3 partial.
    # Compute current count with::
    #
    #   python3 -c "import re; from pathlib import Path; \
    #     P=['getpt','ptsize','UEXIT','NEXIT','FEXIT','CEXIT','DEXIT', \
    #        'P-LEXV','P-PRSO','P-PRSI','PRSA']; \
    #     R=re.compile(r'\\b('+'|'.join(re.escape(p) for p in P)+r')\\b'); \
    #     print(sum(len(R.findall(re.sub(r'#.*','',p.read_text()))) \
    #       for p in Path('moo/bootstrap/zork1/verbs').rglob('*.py') \
    #       if '__pycache__' not in p.parts))"
    BASELINE = 10
    total = 0
    for path in _iter_verb_files():
        text = path.read_text(encoding="utf-8")
        # Strip comments so the dispatch.py quarantine doc and similar
        # don't inflate the count.
        stripped = re.sub(r"#.*", "", text)
        total += len(_PRIMITIVE_RE.findall(stripped))
    assert total <= BASELINE, (
        f"Z-machine primitive count grew from baseline {BASELINE} to {total}. "
        f"A translator change introduced new primitives. Either undo it or "
        f"raise the BASELINE in this test (and document why in "
        f"extras/skills/zork-shakedown/references/open-gaps.md)."
    )


def test_allowlist_does_not_grow_stale() -> None:
    """Files in the allowlist must still exist and still contain primitives.

    Once Phase 3 cleans a file, the file either disappears (god-verb
    decomposition) or no longer references primitives.  Either case means
    the entry can be removed from _KNOWN_PRIMITIVE_LEAKS.  This test makes
    that visible by failing when the allowlist drifts ahead of reality.
    """
    stale: list[str] = []
    for rel in sorted(_KNOWN_PRIMITIVE_LEAKS):
        path = _BOOTSTRAP_DIR / rel
        if not path.exists():
            stale.append(f"{rel}: file no longer exists")
            continue
        text = path.read_text(encoding="utf-8")
        if not _PRIMITIVE_RE.search(text):
            stale.append(f"{rel}: no longer contains primitives")
    if stale:
        pytest.fail("Stale entries in _KNOWN_PRIMITIVE_LEAKS — remove them:\n  " + "\n  ".join(stale))


def test_zil_sdk_templates_have_no_primitives() -> None:
    """The hand-edited templates under ``extras/zil_import/verbs/`` must
    stay clean.  These are copied verbatim into the generated bootstrap;
    any primitive leakage here is ours to fix immediately, not a
    translator-output artifact.

    The ``system/dispatch.py`` file is allowed to mention primitives in
    comments documenting the WALK_VERBS quarantine — we strip comments
    before scanning to avoid false positives.
    """
    template_root = Path(__file__).resolve().parents[1] / "verbs"
    if not template_root.exists():
        pytest.skip(f"templates not present: {template_root}")
    leaks: dict[str, set[str]] = {}
    for path in template_root.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        # Strip comments and docstrings before scanning.  Crude but enough
        # for our templates: drop everything from `#` to EOL, and remove
        # triple-quoted blocks.
        stripped = re.sub(r'""".*?"""', "", text, flags=re.DOTALL)
        stripped = re.sub(r"#.*", "", stripped)
        hits = set(_PRIMITIVE_RE.findall(stripped))
        if hits:
            leaks[str(path.relative_to(template_root))] = hits
    if leaks:
        msg = ["Z-machine primitives in hand-edited templates:"]
        for rel, hits in sorted(leaks.items()):
            msg.append(f"  {rel}: {sorted(hits)}")
        pytest.fail("\n".join(msg))
