"""Generator-level regression tests.

Focused unit tests for ``generator/_gen_objects`` robustness.  The broad
output-shape coverage lives in ``test_bootstrap_consistency.py`` and
``test_translator.py``; this file pins behaviours that are awkward to reach
through a full regen.
"""

from __future__ import annotations

from moo.zil_import.game_config import BEYONDZORK_CONFIG, ZORK1_CONFIG
from moo.zil_import.generator import _gen_exits, _gen_objects
from moo.zil_import.ir import ZilExit, ZilObject, ZilRoom


def _room(atom, *exits):
    return ZilRoom(atom=atom, desc=atom.title(), ldesc=None, fdesc=None, exits=list(exits))


def test_gen_objects_degrades_non_atom_location(caplog):
    """A non-atom (unhashable) location is treated as unplaced, not a crash.

    A mis-parsed direction-exit value could arrive as a list.  The membership
    tests (``loc in rooms`` / ``loc in objects``) would raise ``TypeError:
    unhashable type: 'list'``; the generator must degrade gracefully so one
    malformed object never aborts the whole regen.
    """
    obj = ZilObject(atom="WIDGET", location=["TO", "SOMEWHERE"])
    out = _gen_objects({"WIDGET": obj}, {}, {"WIDGET": "widget"}, ZORK1_CONFIG)
    assert "location=None" in out
    assert "WIDGET" in caplog.text and "non-atom location" in caplog.text


def test_gen_objects_atom_location_unchanged():
    """A well-formed atom location still resolves normally."""
    room = ZilObject(atom="JEWEL", location="CELLAR")
    out = _gen_objects(
        {"JEWEL": room},
        {"CELLAR": object()},  # presence is all _gen_objects checks
        {"JEWEL": "jewel"},
        ZORK1_CONFIG,
    )
    assert "_rooms['CELLAR']" in out


def _exit(direction, **kw):
    return ZilExit(
        direction=direction,
        dest=kw.get("dest"),
        message=kw.get("message"),
        condition=kw.get("condition"),
        else_message=kw.get("else_message"),
        per_routine=kw.get("per_routine"),
    )


def test_xzip_exit_tables_emitted_per_direction():
    """XZIP dialect emits each room exit as a direction-named XTYPE word-table.

    CONNECT=0x0200|len, SCONNECT=0x0300|len (with message), FCONNECT=0x0400|len
    (per-routine).  These feed Beyond Zork's ``<GETP ,HERE ,P?dir>`` reads.
    """
    rooms = {
        "HALL": _room(
            "HALL",
            _exit("NORTH", dest="CAVE"),
            _exit("EAST", dest="CAVE", message="You stroll east."),
            _exit("DOWN", per_routine="CLIMB-F"),
            _exit("WEST", message="A wall blocks the way."),
        ),
        "CAVE": _room("CAVE"),
    }
    out = _gen_exits(rooms, BEYONDZORK_CONFIG)
    assert "set_property('north', [513, _r_cave])" in out  # CONNECT|1
    assert "set_property('east', [769, _r_cave, 'You stroll east.'])" in out  # SCONNECT|1
    assert "set_property('down', [1025, 'CLIMB-F'])" in out  # FCONNECT|1
    assert "set_property('west', [1536, 'A wall blocks the way.'])" in out  # SORRY-EXIT


def test_ezip_emits_no_direction_exit_tables():
    """EZIP (default) does not emit XTYPE direction properties — exit objects only."""
    rooms = {"HALL": _room("HALL", _exit("NORTH", dest="CAVE")), "CAVE": _room("CAVE")}
    out = _gen_exits(rooms)  # cfg=None → exit_tables defaults off
    assert "set_property('north'" not in out
    assert "_classes['exit']" in out  # exit objects still emitted
