"""
Tests for the ZIL daemon tick-mode classifier and the generator's
ACTORBIT branching / template surface.

The classifier decides whether a translated ``<QUEUE I-FOO N>`` lands
on the native real-time scheduler (Celery Beat ``PeriodicTask``) or
the per-player turn queue (``zstate_queue``).  The generator branches
ACTORBIT objects between ``Actor`` (player-character placeholders)
and ``Actor NPC`` (real NPCs that should get an anonymous
``Player`` record and inherit the ``act`` personality hook).
"""

from __future__ import annotations

from moo.zil_import.game_config import ZORK1_CONFIG
from moo.zil_import.generator import (
    _gen_daemons,
    _render_classes_module,
)
from moo.zil_import.translator import daemon_modes


def test_realtime_routines_cover_known_event_driven_daemons():
    """Every routine we've classified as real-time-safe (event-driven,
    scope-checked, or one-shot) returns ``"realtime"``.  Scope-bound
    daemons (i-forest-room) are safe in realtime mode because the
    scheduler's ``tick_realtime`` wrapper honours False-return as
    "drop me from the schedule"."""
    for name in (
        "i-thief",
        "i-forest-room",
        "i-match",
        "i-xb",
        "i-xbh",
        "i-xc",
        "i-maint-room",
    ):
        assert daemon_modes.classify(name) == "realtime", f"{name} should be realtime"


def test_turn_accurate_daemons_default_to_turn_mode():
    """Fuel decay (lantern, candles), healing (cure), rage (cyclops),
    per-round combat (fight), boat drift (river), tide flips (rfill/rempty),
    and sword glow updates must stay on the turn queue so their
    per-action cadence isn't lost under wall-clock scheduling."""
    for name in (
        "i-lantern",
        "i-candles",
        "i-cure",
        "i-cyclops",
        "i-fight",
        "i-river",
        "i-rfill",
        "i-rempty",
        "i-sword",
    ):
        assert daemon_modes.classify(name) == "turn", f"{name} should be turn"


def test_unknown_routine_defaults_to_turn():
    """An unclassified routine name preserves the safe (turn) default
    so a future ZIL port that adds a daemon doesn't silently jump onto
    real-time scheduling."""
    assert daemon_modes.classify("i-something-new") == "turn"
    assert daemon_modes.classify("i-fuel-burn") == "turn"


def test_classifier_is_case_insensitive():
    """ZIL atoms come in upper-kebab; downstream emitters lowercase
    them. The classifier accepts either casing."""
    assert daemon_modes.classify("I-THIEF") == "realtime"
    assert daemon_modes.classify("I-LANTERN") == "turn"


def test_player_avatar_atoms_exclude_real_npcs():
    """The denylist covers the four ZIL placeholder atoms that name
    the player-character; real NPCs (thief, troll, etc.) must stay
    OFF the list so they get the NPC parent + Player record."""
    for atom in ("ME", "ADVENTURER", "PLAYER", "WINNER"):
        assert atom in ZORK1_CONFIG.player_avatar_atoms
    for atom in ("THIEF", "TROLL", "CYCLOPS", "BAT", "GHOSTS"):
        assert atom not in ZORK1_CONFIG.player_avatar_atoms


def test_classes_template_defines_actor_npc():
    """``010_classes.py`` declares the NPC class and adds it to the
    ``_classes`` map so the ACTORBIT-branch parent lookup resolves."""
    rendered = _render_classes_module()
    assert "Actor NPC" in rendered
    assert '"actor_npc": actor_npc' in rendered


def test_daemons_module_clears_realtime_pts_and_sweeps_marker():
    """``050_daemons.py`` deletes ``zil-daemon:``-marked PeriodicTasks
    (plus the legacy ``zork1-daemon:`` prefix for a clean transition)
    and resets the System Object's ``_realtime_pts`` registry — both
    necessary for ``--sync`` idempotency."""
    rendered = _gen_daemons()
    assert "from django_celery_beat.models import PeriodicTask" in rendered
    assert "description__startswith='zil-daemon:'" in rendered
    assert "description__startswith='zork1-daemon:'" in rendered
    assert "_.set_property('_realtime_pts', {})" in rendered
    # The ``.delete()`` return tuple must NOT unpack into ``_`` because
    # that would shadow the System Object reference and break the
    # subsequent ``_.set_property`` call (caught in production sync).
    assert "_swept, _ =" not in rendered
