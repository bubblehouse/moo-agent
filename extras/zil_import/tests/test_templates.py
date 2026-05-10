"""Tests for the Jinja templates under ``extras/zil_import/templates/``.

See :doc:`/reference/zil-importer` (Generator) for how each template is
consumed.
"""

from __future__ import annotations

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
        "zork_root",
        "zork_thing",
        "zork_container",
        "zork_room",
        "zork_actor",
        "zork_exit",
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
    assert body.startswith('#!moo verb walk go n s --on "Zork Actor" --dspec either')
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
    assert body.startswith('#!moo verb climb scale --on "Zork Actor" --dspec either')
    assert "_.walk(target)" in body
    assert '_.walk("up")' in body


def test_classes_template_byte_stable() -> None:
    """Two consecutive renders produce identical bytes (no nondeterminism)."""
    first = _render_classes_module()
    second = _render_classes_module()
    assert first == second
