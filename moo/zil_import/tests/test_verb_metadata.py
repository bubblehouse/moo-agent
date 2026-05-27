"""Unit tests for ``moo.zil_import.verb_metadata``."""

from __future__ import annotations

from pathlib import Path

import pytest

from moo.zil_import.verb_metadata import (
    body_perform_targets,
    body_player_verb_literals,
    body_references_prsi,
    parse_verb_file,
)


def test_parse_verb_file_round_trip(tmp_path: Path) -> None:
    src = tmp_path / "v.py"
    src.write_text(
        '#!moo verb take get pick --on "satchel" --dspec any --ispec on:this in:this\n'
        "from moo.sdk import context\n"
        "print('ok')\n"
    )
    result = parse_verb_file(src)
    assert result is not None
    shebang, body = result
    assert shebang.names == ("take", "get", "pick")
    assert shebang.on == "satchel"
    assert shebang.dspec == "any"
    assert shebang.ispec == {"on": "this", "in": "this"}
    assert "print('ok')" in body
    assert body.startswith("from moo.sdk")


def test_parse_verb_file_no_shebang(tmp_path: Path) -> None:
    src = tmp_path / "v.py"
    src.write_text("# just a comment\nprint('nope')\n")
    assert parse_verb_file(src) is None


def test_body_player_verb_literals_eq() -> None:
    body = "if the_player_verb == 'take':\n    pass\nelif the_player_verb == 'drop':\n    pass\n"
    assert body_player_verb_literals(body) == {"take", "drop"}


def test_body_player_verb_literals_in_list() -> None:
    body = "if the_player_verb in ['take', 'get', 'pick']:\n    pass\n"
    assert body_player_verb_literals(body) == {"take", "get", "pick"}


def test_body_player_verb_literals_in_tuple() -> None:
    body = "if the_player_verb in ('hello', 'hi'):\n    pass\n"
    assert body_player_verb_literals(body) == {"hello", "hi"}


def test_body_player_verb_literals_mixed() -> None:
    body = (
        "if the_player_verb == 'examine':\n"
        "    pass\n"
        "elif the_player_verb in ['take', 'get']:\n"
        "    pass\n"
        "elif the_player_verb in ('break', 'smash'):\n"
        "    pass\n"
    )
    assert body_player_verb_literals(body) == {"examine", "take", "get", "break", "smash"}


def test_body_player_verb_literals_ignores_unrelated_strings() -> None:
    body = "print('the_player_verb is a value')\n"
    assert body_player_verb_literals(body) == set()


def test_body_perform_targets_system_form() -> None:
    body = "_.perform('block_with', this, prso)\n_.perform('stand_before', this, None)\n"
    targets = body_perform_targets(body)
    assert (target_name for target_name, _ in targets)
    assert {name for name, _ in targets} == {"block_with", "stand_before"}


def test_body_perform_targets_object_form() -> None:
    body = "exit.perform('move', source, dest)\n"
    targets = body_perform_targets(body)
    assert targets == [("move", 1)]


def test_body_perform_targets_line_numbers() -> None:
    body = "x = 1\ny = 2\n_.perform('foo', a, b)\nz = 3\n_.perform('bar', a, b)\n"
    targets = body_perform_targets(body)
    assert targets == [("foo", 3), ("bar", 5)]


def test_body_references_prsi_iobj_getter() -> None:
    assert body_references_prsi("prsi = parser.get_iobj() if parser.has_iobj() else None\n")


def test_body_references_prsi_eq_check() -> None:
    assert body_references_prsi("if prsi == this:\n    pass\n")


def test_body_references_prsi_attribute_access() -> None:
    assert body_references_prsi("prsi.desc()\n")


def test_body_references_prsi_pobj_str() -> None:
    assert body_references_prsi("if parser.has_pobj_str('with'):\n    pass\n")


def test_body_references_prsi_no_iobj() -> None:
    assert not body_references_prsi("prso = parser.get_dobj()\nprint(prso)\n")
