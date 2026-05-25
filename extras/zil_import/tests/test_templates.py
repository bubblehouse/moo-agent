"""Tests for the Jinja templates under ``extras/zil_import/templates/``.

See :doc:`/reference/zil-importer` (Generator) for how each template is
consumed.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from extras.zil_import.game_config import ZORK1_CONFIG
from extras.zil_import.generator import (
    _GENERATED_HEADER,
    _gen_bootstrap_init,
    _jinja_env,
    _render_classes_module,
)


_TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "templates"


def test_templates_directory_exists() -> None:
    """The templates directory exists with all four .j2 files in place."""
    assert _TEMPLATE_DIR.is_dir(), f"templates dir missing: {_TEMPLATE_DIR}"
    expected = {
        "010_classes.py.j2",
        "bootstrap.py.j2",
        "walk_dispatcher.py.j2",
        "climb_dispatcher.py.j2",
    }
    actual = {p.name for p in _TEMPLATE_DIR.glob("*.j2")}
    missing = expected - actual
    assert not missing, f"missing templates: {sorted(missing)}"


def test_classes_template_renders() -> None:
    """``010_classes.py`` carries the header and every canonical class."""
    rendered = _render_classes_module()
    assert rendered.startswith(_GENERATED_HEADER)
    for class_var in (
        "root",
        "thing",
        "container",
        "room",
        "actor",
        "actor_npc",
        "exit",
    ):
        assert f'"{class_var}": {class_var},' in rendered, f"{class_var} not in _classes dict"
    assert 'log.info("Zork classes: %d created/updated", len(_classes))' in rendered


def test_bootstrap_template_carries_dataset_and_manifest() -> None:
    """``bootstrap.py`` interpolates the dataset name and manifest list."""
    rooms = {f"R{i}": object() for i in range(7)}
    objects = {f"O{i}": object() for i in range(13)}
    rendered = _gen_bootstrap_init(rooms, objects, ZORK1_CONFIG)
    assert _GENERATED_HEADER in rendered
    assert f"manage.py moo_init --bootstrap {ZORK1_CONFIG.dataset_name}" in rendered
    assert " / ".join(ZORK1_CONFIG.manifest_files) in rendered
    assert "Rooms:   7" in rendered
    assert "Objects: 13" in rendered
    assert f"_repo = bootstrap.initialize_dataset({ZORK1_CONFIG.dataset_name!r})" in rendered


def test_walk_dispatcher_template_renders() -> None:
    """The walk dispatcher emits a shebang plus the ``_.walk(...)`` calls."""
    body = _jinja_env.get_template("walk_dispatcher.py.j2").render(
        walk_names="walk go n s",
        header=_GENERATED_HEADER,
        pylint_disable="# pylint: disable=foo",
        verb="WALK",
        dir_set_repr="{'n', 's'}",
    )
    assert body.startswith('#!moo verb walk go n s --on "Actor" --dspec either')
    assert _GENERATED_HEADER in body
    assert "_.walk(parser.get_dobj_str())" in body
    assert "_.walk(verb_name)" in body


def test_climb_dispatcher_template_renders() -> None:
    """The climb dispatcher includes the canonical Zork tree/ladder fallback."""
    body = _jinja_env.get_template("climb_dispatcher.py.j2").render(
        names="climb scale",
        header=_GENERATED_HEADER,
        pylint_disable="# pylint: disable=foo",
        verb="CLIMB",
    )
    assert body.startswith('#!moo verb climb scale --on "Actor" --dspec either')
    assert "_.walk(target)" in body
    assert '_.walk("up")' in body


def test_classes_template_byte_stable() -> None:
    """Two consecutive renders produce identical bytes (no nondeterminism)."""
    first = _render_classes_module()
    second = _render_classes_module()
    assert first == second


# ---------------------------------------------------------------------------
# Hand-written verb templates under extras/zil_import/verbs/
#
# Each of these is a hand-written replacement that wins over the
# auto-translator's emission because the generator's ``_write_unique``
# refuses to overwrite an existing file.  The tests below verify the
# files are present and parse as valid Python — catches editor mishaps
# and renames that would silently revert the bootstrap to the broken
# auto-emitted version.
# ---------------------------------------------------------------------------

_VERBS_DIR = Path(__file__).resolve().parents[1] / "verbs"


@pytest.mark.parametrize(
    "relpath",
    [
        # Bug 1: give-to-me recursion guard
        "thing/substrate_pre/pre_sgive.py",
        # Bug 5: Living Room turnfunc prso null guard
        "rooms/living_room/turnfunc.py",
        # Bug 9: vowel-aware article in inventory and open-container listings
        "thing/output/describe_object.py",
        "thing/output/print_contents.py",
        # Bug 10: examine/eat self-target guards
        "thing/substrate_verbs/examine.py",
        "thing/substrate_verbs/eat.py",
        # Bug 11+12: put-in iobj rejection ladder
        "thing/substrate_verbs/put.py",
    ],
)
def test_handwritten_verb_template_exists_and_parses(relpath: str) -> None:
    """The hand-written replacement under ``verbs/`` exists and is
    syntactically valid Python.  Verb-body sandbox rules (no leading
    underscore locals, no ``return`` at module top-level outside the
    sandbox runner) are not validated here — only Python-level syntax.
    """
    path = _VERBS_DIR / relpath
    assert path.exists(), f"hand-written template missing: {path}"
    source = path.read_text(encoding="utf-8")
    # Skip the ``#!moo verb …`` shebang on the first line; ast.parse is
    # fine with it since ``#`` is just a comment.
    ast.parse(source, filename=str(path))
