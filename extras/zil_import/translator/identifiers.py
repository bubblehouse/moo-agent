"""
Pure-function helpers for identifier sanitization and verb headers.

Stateless: take ZIL atom strings (or generated body lines) and return
Python-safe forms.  See :doc:`/reference/zil-importer` (Identifier
sanitization) for the full rule set.
"""

from __future__ import annotations

import re
from pathlib import Path

from .constants import (
    DISABLE_FULL,
    DISABLE_INTRINSIC,
    PY_BUILTIN_SHADOWS,
    PY_KEYWORDS,
)


# Maps substrate verb owner-class (from the ``--on "..."`` shebang) to the
# Python expression the translator should dispatch routine calls through.
# ``Zork Thing`` is the default fallback (auto-translated routines), so it
# isn't listed here.  Verbs on ``Zork Actor`` / ``Zork Root`` go through the
# player (which inherits from both); System Object verbs go through ``_``.
_SUBSTRATE_OWNER_DISPATCH: dict[str, str] = {
    "Zork Actor": "context.player",
    "Zork Root": "context.player",
    "System Object": "_",
}

_SHEBANG_RE = re.compile(r'^#!moo verb\s+([^\n]*?)\s+--on\s+"([^"]+)"')

# Built lazily on first ``substrate_receiver`` call; the importer ships its
# substrate verbs in a fixed location so a single scan suffices per process.
_SUBSTRATE_DISPATCH_CACHE: dict[str, str] = {}


def substrate_receiver(name: str) -> str:
    """
    Return the dispatch receiver for a substrate routine call.

    Looks up ``name`` (snake-case verb name, e.g. ``"echo"``) in the
    cached substrate-owner map and returns the Python expression to
    invoke it on (``context.player`` for Zork Actor / Root verbs,
    ``_`` for System Object verbs).  Unknown names default to
    ``_.zork_thing`` — the auto-translated routines all live there.

    :param name: Snake-case verb name to look up.
    :returns: The dispatch receiver expression.
    """
    if not _SUBSTRATE_DISPATCH_CACHE:
        _SUBSTRATE_DISPATCH_CACHE.update(scan_substrate_owners())
    return _SUBSTRATE_DISPATCH_CACHE.get(name, "_.zork_thing")


def register_substrate_overrides(overrides: dict[str, str]) -> None:
    """
    Pre-seed the substrate-dispatch cache with caller-supplied overrides.

    Used by the generator to mark relocated routines whose owner can't be
    inferred by the filesystem scan because the substrate file is created
    by the translator itself (e.g. V-SCORE relocates from Zork Thing to
    Zork Actor, but ``extras/zil_import/verbs/zork_actor/score.py``
    doesn't exist in the source tree — it's a regen output).

    Idempotent.  Call before any ``substrate_receiver`` use.

    :param overrides: Mapping of snake-case verb name → dispatch receiver
        expression (e.g. ``"score": "context.player"``).
    """
    if not _SUBSTRATE_DISPATCH_CACHE:
        _SUBSTRATE_DISPATCH_CACHE.update(scan_substrate_owners())
    _SUBSTRATE_DISPATCH_CACHE.update(overrides)


def reset_substrate_cache() -> None:
    """
    Clear the substrate-dispatch cache.  Test-only escape hatch so the
    next ``substrate_receiver`` call re-scans the filesystem.
    """
    _SUBSTRATE_DISPATCH_CACHE.clear()


def scan_substrate_owners(verbs_dir: Path | None = None) -> dict[str, str]:
    """
    Walk the substrate ``verbs/`` tree and map each verb name → dispatch expr.

    Used by ``ZilTranslator._translate_atom`` to route routine calls to the
    class that actually owns the substrate verb (e.g. ``echo`` lives on
    ``Zork Actor``, not ``Zork Thing``, so the call must dispatch via
    ``context.player.echo()`` rather than ``_.zork_thing.echo()``).

    :param verbs_dir: Path to the substrate ``verbs/`` directory.  Defaults
        to the importer's own ``verbs/`` next to this module's package.
    :returns: Mapping of verb name → dispatch expression for non-default
        owner classes.  Verbs on ``Zork Thing`` (the default) are omitted.
    """
    if verbs_dir is None:
        verbs_dir = Path(__file__).resolve().parent.parent / "verbs"
    out: dict[str, str] = {}
    for path in verbs_dir.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        try:
            first_line = path.read_text(encoding="utf-8").split("\n", 1)[0]
        except OSError:
            continue
        m = _SHEBANG_RE.match(first_line)
        if not m:
            continue
        names_blob, owner = m.group(1), m.group(2)
        dispatch = _SUBSTRATE_OWNER_DISPATCH.get(owner)
        if dispatch is None:
            continue
        for name in names_blob.split():
            out[name] = dispatch
    return out


def pylint_disable_line(*, lint_active: bool) -> str:
    """
    Return the ``# pylint: disable=...`` line for a generated verb file.

    :param lint_active: When ``True``, emit only the format-intrinsic
        disables; when ``False``, emit the broader tolerant set.
    :returns: A single-line pylint-disable comment.
    """
    return "# pylint: disable=" + (DISABLE_INTRINSIC if lint_active else DISABLE_FULL)


def verb_attr_safe(name: str) -> bool:
    """
    True when a verb name can be invoked via attribute access.

    Object.__getattr__ resolves dotted access only for valid Python
    identifiers; hyphenated names must keep using ``invoke_verb``.

    :param name: Verb name to test.
    :returns: ``True`` if ``name`` is dot-syntax safe.
    """
    return name.isidentifier() and name not in PY_KEYWORDS


def predicate_python_name(zil_name: str) -> str | None:
    """
    Convert a ``?``-suffixed predicate atom to its ``is_<snake>`` form.

    :param zil_name: The ZIL atom to convert.
    :returns: The ``is_<snake>`` form, or ``None`` for non-predicates and
        built-in operators like ``EQUAL?`` / ``IN?`` / ``0?`` (handled by
        other rules).
    """
    if not zil_name.endswith("?"):
        return None
    base = zil_name[:-1]
    if not base or not base[0].isalpha():
        return None
    snake = base.lower().replace("-", "_")
    return f"is_{snake}"


def routine_dot_name(zil_name: str) -> str | None:
    """
    Return the dot-syntax-safe name for a ZIL routine, or ``None``.

    Drops the ``v-`` substrate prefix, snake-cases hyphens, and routes
    predicates through ``predicate_python_name``.

    :param zil_name: The ZIL routine name (UPPER-KEBAB-CASE).
    :returns: The dot-syntax-safe form, or ``None`` when the name still
        collides with a keyword or contains non-identifier characters
        (callers fall back to ``invoke_verb`` in that case).
    """
    pred = predicate_python_name(zil_name)
    if pred is not None:
        return pred
    name = zil_name.lower()
    if name.startswith("v-"):
        name = name[2:]
    snake = name.replace("-", "_")
    if verb_attr_safe(snake):
        return snake
    return None


def sanitize_ident(name: str) -> str:
    """
    Convert a ZIL atom into a valid Python identifier.

    See :doc:`/reference/zil-importer` (Identifier sanitization) for the
    full rule set.

    :param name: The ZIL atom to sanitize.
    :returns: A valid, non-shadowing Python identifier.
    """
    raw = name.lstrip(".")
    out = raw.lower().replace("-", "_").replace("?", "_p")
    out = re.sub(r"[^a-z0-9_]", "_", out)
    if out and out[0].isdigit():
        out = "v_" + out
    if not out:
        # RestrictedPython rejects `_xxx` locals; sentinel matches keyword convention.
        return "unknown_v"
    if out in PY_KEYWORDS or out in PY_BUILTIN_SHADOWS:
        out = out + "_v"
    # RestrictedPython rejects any `_`-prefixed local — strip defensively.
    while out.startswith("_"):
        out = out.lstrip("_") + "_v"
        if not out.replace("_v", ""):
            out = "ident" + out
    return out


def as_object(expr: str) -> str:
    """
    Wrap a quoted-atom expression in ``lookup()`` for attribute access.

    :param expr: A Python expression string, possibly a quoted atom literal.
    :returns: ``lookup("name")`` for quoted atoms; ``expr`` unchanged
        otherwise.
    """
    stripped = expr.strip()
    if (
        len(stripped) >= 2
        and stripped[0] in ("'", '"')
        and stripped[-1] == stripped[0]
        and stripped.count(stripped[0]) == 2
    ):
        atom = stripped[1:-1]
        return f'lookup("{atom.lower().replace("-", " ")}")'
    return stripped


def ends_in_unconditional_return(body_lines: list[str]) -> bool:
    """
    True if the body unconditionally returns at its tail.

    Used to suppress redundant ``return passthrough()`` appends that
    would trip pylint's ``unreachable-code`` (W0101).  Recognises two
    shapes:

    1. The last meaningful line at the body's outer indent is itself
       ``return``.
    2. The body's trailing construct is an ``if``/``elif``/``else``
       chain with an ``else`` arm where every branch ends in an
       unconditional return (recursively).

    :param body_lines: Generated body lines to inspect.
    :returns: ``True`` if the body already ends in an unconditional return.
    """
    last_idx = None
    for i in range(len(body_lines) - 1, -1, -1):
        stripped = body_lines[i].lstrip()
        if stripped and not stripped.startswith("#"):
            last_idx = i
            break
    if last_idx is None:
        return False
    last = body_lines[last_idx]
    stripped = last.lstrip()
    if last[: len(last) - len(stripped)] == "":
        return stripped.startswith("return") and (
            len(stripped) == len("return") or stripped[len("return")] in (" ", "\n")
        )
    return _trailing_chain_exhaustive(body_lines)


def _trailing_chain_exhaustive(body_lines: list[str]) -> bool:
    """
    True when the trailing ``if/elif/else`` chain at outer indent has an
    ``else`` arm and every branch ends in an unconditional return.
    """
    chain_openers: list[int] = []
    has_else = False
    for i in range(len(body_lines) - 1, -1, -1):
        line = body_lines[i]
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        if line[: len(line) - len(stripped)]:
            continue
        if stripped.startswith("else") and (len(stripped) == len("else") or stripped[len("else")] in (":", " ")):
            chain_openers.append(i)
            has_else = True
            continue
        if stripped.startswith("elif "):
            chain_openers.append(i)
            continue
        if stripped.startswith("if "):
            chain_openers.append(i)
            break
        return False
    if not has_else or not chain_openers:
        return False
    chain_openers.reverse()
    for k, opener_idx in enumerate(chain_openers):
        next_opener = chain_openers[k + 1] if k + 1 < len(chain_openers) else len(body_lines)
        branch = []
        for bl in body_lines[opener_idx + 1 : next_opener]:
            if bl.strip() == "":
                branch.append("")
            elif bl.startswith("    "):
                branch.append(bl[4:])
            else:
                return False
        if not ends_in_unconditional_return(branch):
            return False
    return True
