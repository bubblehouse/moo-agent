"""
Verb-file metadata reader for generated bootstrap output.

Two consumers: the bootstrap-consistency test
(``tests/test_bootstrap_consistency.py``) walks ``moo/bootstrap/<dataset>/``
to assert shebang/body alignment, and any future CLI lint pass.

Shebang parsing reuses ``moo.bootstrap.parse_shebang`` so the engine and
this reader stay in lockstep on grammar.

Background: HHG shakedown surfaced multiple bugs where the verb shebang
disagreed with the body (compound-particle verb names like ``lie-down``
in the body but ``lie_down`` in the shebang; ``--dspec this`` on a verb
whose body reads ``prsi == this``; ``_.perform('X', …)`` calls where
``X`` was never registered as a verb). All three classes are static
properties of the generated tree that the tests in
``test_bootstrap_consistency.py`` enforce.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from moo.bootstrap import parse_shebang


@dataclass(frozen=True)
class VerbShebang:
    """Parsed ``#!moo verb`` line."""

    names: tuple[str, ...]
    on: str
    dspec: str
    ispec: dict[str, str]


def parse_verb_file(path: Path) -> tuple[VerbShebang, str] | None:
    """
    Parse a verb file's shebang line.

    :param path: Verb file path. Read once; first line scanned for
        ``#!moo verb`` and the rest returned as the body.
    :returns: ``(shebang, body)`` tuple, or ``None`` if the file has no
        shebang.
    """
    contents = path.read_text(encoding="utf8")
    parsed = parse_shebang(contents)
    if parsed is None:
        return None
    names, on, dspec, ispec = parsed
    body = contents.split("\n", 1)[1] if "\n" in contents else ""
    return VerbShebang(tuple(names), on, dspec, ispec or {}), body


def iter_verb_files(bootstrap_root: Path) -> Iterator[tuple[Path, VerbShebang, str]]:
    """
    Walk every ``.py`` under ``<bootstrap_root>/verbs/`` and yield the
    ones with a valid shebang.

    :param bootstrap_root: Directory containing ``verbs/`` (e.g.
        ``moo/bootstrap/zork1``).
    """
    verbs_dir = bootstrap_root / "verbs"
    if not verbs_dir.is_dir():
        return
    for path in sorted(verbs_dir.rglob("*.py")):
        if path.name == "__init__.py":
            continue
        result = parse_verb_file(path)
        if result is None:
            continue
        shebang, body = result
        yield path, shebang, body


# Match ``the_player_verb == 'X'`` and the membership forms
# ``the_player_verb in ['X', 'Y']``, ``the_player_verb in ('X',)`` and
# ``in {'X'}`` (the body emits any of these depending on clause shape).
_EQ_LITERAL_RE = re.compile(r"the_player_verb\s*==\s*['\"]([^'\"]+)['\"]")
_IN_LITERAL_RE = re.compile(r"the_player_verb\s+in\s+[\[\(\{]([^\]\)\}]+)[\]\)\}]")
_STR_LITERAL_RE = re.compile(r"['\"]([^'\"]+)['\"]")


def body_player_verb_literals(body: str) -> set[str]:
    """
    Collect every string literal compared against ``the_player_verb``.

    Used by the alignment test: every literal returned here must appear
    in the shebang's ``names`` list, otherwise the body has a branch
    that the player can never trigger.
    """
    out: set[str] = set()
    for m in _EQ_LITERAL_RE.finditer(body):
        out.add(m.group(1))
    for m in _IN_LITERAL_RE.finditer(body):
        for lit_match in _STR_LITERAL_RE.finditer(m.group(1)):
            out.add(lit_match.group(1))
    return out


# Match ``_.perform('X', …)`` and ``<obj>.perform('X', …)`` (the
# translator emits both shapes — System-level via ``_.perform`` for
# substrate routing, and object-level via ``<obj>.perform`` when an
# action handler re-dispatches to itself with different PRSO/PRSI).
_PERFORM_RE = re.compile(r"(?:^|[^A-Za-z0-9_])(?:_\.|\w+\.)perform\(\s*['\"]([^'\"]+)['\"]")


def body_perform_targets(body: str) -> list[tuple[str, int]]:
    """
    Return ``(verb_name, line_number)`` for every ``.perform('X', …)`` call.

    Line numbers are 1-based, counted from the start of ``body`` (which
    is body-only, starting after the shebang). Used by the
    perform-target resolution test.

    Skips lines that are pure comments (first non-whitespace char is ``#``).
    Lint should not flag calls in documentation prose.
    """
    out: list[tuple[str, int]] = []
    lines = body.split("\n")
    for m in _PERFORM_RE.finditer(body):
        perform_pos = body.index("perform", m.start(), m.end())
        line_no = body.count("\n", 0, perform_pos) + 1
        if 1 <= line_no <= len(lines) and lines[line_no - 1].lstrip().startswith("#"):
            continue
        out.append((m.group(1), line_no))
    return out


# Conservative substring checks: ``parser.get_iobj()``, ``has_iobj()``,
# ``has_pobj_str(``, plus any ``prsi`` reference. False positives are
# acceptable because the test only uses this to demand ``--ispec`` on
# verbs that look like they might branch on the iobj.
_PRSI_MARKERS = (
    "parser.get_iobj",
    "parser.has_iobj",
    "parser.get_pobj",
    "parser.has_pobj_str",
    "prsi ==",
    "prsi.",
    "prsi in ",
    "prsi is ",
)


def body_references_prsi(body: str) -> bool:
    """True if the body looks like it inspects the indirect object."""
    return any(marker in body for marker in _PRSI_MARKERS)
