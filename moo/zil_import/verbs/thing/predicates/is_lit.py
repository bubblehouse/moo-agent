#!moo verb is_lit --on "Thing" --dspec this
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Replacement for canonical LIT? — walks the player inventory and the
target room for ONBIT objects (lit lantern, candles, torch, matches)
and returns True if any are lit.  The canonical body uses parser-
internal tables (P-MERGE / P-SLOCBITS / DO-SL / P-MATCHLEN) that
DjangoMOO doesn't materialize, so calls into the auto-translated
LIT? would crash on uninitialised state.

Args:
    args[0] = the room to test (defaults to the player's current room)
    args[1] = RMBIT (canonical "test the room's own ONBIT" — defaults
              to True; only LIT? callers from V-FLIP-ROOM-LIGHT pass
              False to skip the room-level check)

The ALWAYS-LIT short-circuit is preserved so existing reset-state
seeds (`zstate_always_lit = True`) keep their behaviour.  Once enough
ONBIT objects are wired up across rooms (lantern lit/unlit, candles
burning, torch carried) the reset can drop the seed and rely on this
predicate alone.
"""

from moo.sdk import context

player = context.player
rm = args[0] if len(args) > 0 else player.location
rmbit = args[1] if len(args) > 1 else True

if player.zstate_get("ALWAYS-LIT"):
    return True

if rm is None:
    return False

# Room-level light: ONBIT (e.g. surface rooms), RLIGHTBIT (rooms that
# carry their own permanent illumination), or OUTDOOR (surface rooms
# the bootstrap doesn't flag with ONBIT but are obviously sunlit).
if rmbit:
    if rm.flag("onbit") or rm.flag("rlightbit") or rm.flag("outdoor"):
        return True

# Carried light source.
for item in player.contents.all():
    if item.flag("onbit"):
        return True

# Light source already on the floor of the room.
for item in rm.contents.all():
    if item == player:
        continue
    if item.flag("onbit"):
        return True

return False
