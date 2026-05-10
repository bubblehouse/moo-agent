"""GameConfig tests.

The translator and generator are designed to be game-agnostic; per-game
strings live in ``GameConfig`` and are threaded through both engines.
These tests pin that contract so a future regression that re-hardcodes
``"Zork 1"`` etc. into the engine fails immediately.
"""

from __future__ import annotations

from extras.zil_import.converter import _extract_routine
from extras.zil_import.game_config import ZORK1_CONFIG, GameConfig
from extras.zil_import.parser import parse, tokenize
from extras.zil_import.translator import translate_routine


def _routine(src: str):
    return _extract_routine(parse(tokenize(src))[0])


# ---------------------------------------------------------------------------
# Default Zork 1 instance
# ---------------------------------------------------------------------------


def test_zork1_config_defaults():
    cfg = ZORK1_CONFIG
    assert cfg.name == "Zork 1"
    assert cfg.dataset_name == "zork1"
    assert "ZORK I" in cfg.banner
    assert "{rooms}" in cfg.banner
    assert "{objects}" in cfg.banner
    assert cfg.manifest_files == ("dungeon.zil", "actions.zil")
    assert "Infocom" in cfg.license_blurb


def test_zork1_npc_atom_map_covers_canonical_villains():
    """The canonical villains (THIEF/TROLL/CYCLOPS) must round-trip
    through the translator as ``lookup("...")`` calls."""
    npcs = ZORK1_CONFIG.npc_atom_map
    assert npcs["THIEF"] == "thief"
    assert npcs["TROLL"] == "troll"
    assert npcs["CYCLOPS"] == "cyclops"
    # ROBBER aliases THIEF — both resolve to the same object name.
    assert npcs["ROBBER"] == "thief"


# ---------------------------------------------------------------------------
# Translator integration
# ---------------------------------------------------------------------------


def test_translator_emits_npc_lookup_for_zork1_atom():
    """``,THIEF`` references translate to ``lookup("thief")`` when the
    Zork 1 config is active (the default)."""
    out = translate_routine(_routine("<ROUTINE FOO () <FSET ,THIEF ,ONBIT>>"))
    assert 'lookup("thief")' in out


def test_translator_uses_custom_npc_atom_map():
    """A custom ``GameConfig`` overrides the NPC mapping without touching
    the translator core."""
    custom = GameConfig(
        name="Generic Game",
        dataset_name="generic",
        banner="generic banner",
        manifest_files=("game.zil",),
        license_blurb="custom",
        npc_atom_map={"GUARD": "city guard"},
    )
    out = translate_routine(_routine("<ROUTINE FOO () <FSET ,GUARD ,ONBIT>>"), game_config=custom)
    assert 'lookup("city guard")' in out
    # The canonical Zork mapping is *not* present — proves the translator
    # core is not hardcoded.
    assert 'lookup("thief")' not in out


def test_translator_falls_back_to_zstate_for_unknown_atom():
    """An atom not in the NPC map still translates (via the zstate path).
    Anchors that the npc_atom_map is purely additive."""
    custom = GameConfig(
        name="Empty",
        dataset_name="empty",
        banner="b",
        manifest_files=("x.zil",),
        license_blurb="",
        npc_atom_map={},
    )
    out = translate_routine(
        _routine("<ROUTINE FOO () <SETG WIDGET 1>>"),
        game_config=custom,
    )
    # WIDGET isn't an NPC; it's a zstate slot.
    assert "WIDGET" in out


# ---------------------------------------------------------------------------
# Banner formatting
# ---------------------------------------------------------------------------


def test_banner_format_substitutes_room_object_counts():
    """The banner template must accept ``{rooms}`` / ``{objects}``
    placeholders so the generator can render the live counts."""
    rendered = ZORK1_CONFIG.banner.format(rooms=110, objects=140)
    assert "110 rooms" in rendered
    assert "140 objects" in rendered


# ---------------------------------------------------------------------------
# Frozen dataclass — config is immutable
# ---------------------------------------------------------------------------


def test_game_config_is_frozen():
    """``GameConfig`` is a frozen dataclass so callers can pass instances
    around without worrying about mutation."""
    import dataclasses

    assert dataclasses.is_dataclass(GameConfig)
    cfg = ZORK1_CONFIG
    try:
        cfg.name = "should fail"  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        pass
    else:
        raise AssertionError("GameConfig should be frozen")
