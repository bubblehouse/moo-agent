#!moo verb hit_spot --on "Zork Thing" --dspec either
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Hand-written HIT-SPOT replacement.

Canonical ZIL hit_spot removes the drinkable object from its container
when consumed.  The auto-translated body's condition (``prso == water
AND NOT global_water.global_in(here)``) skips removal in the Kitchen
because global_water IS reachable there — so repeated ``drink water``
from the bottle never depletes it.

Replacement:
- If prso is a discrete drinkable Object (location is a container the
  player holds), remove it from its container.
- Otherwise (global water source like the reservoir or kitchen tap), no
  remove — drinking from an environmental source doesn't deplete it.

The thirst-quenched response stays the same.
"""

from moo.sdk import NoSuchObjectError, context

parser = context.parser
try:
    prso = parser.get_dobj() if parser.has_dobj_str() else None
except NoSuchObjectError:
    prso = None

player = context.player

if prso is not None and prso.location is not None and prso.location != player.here():
    # A drinkable inside a container the player holds (e.g. water in
    # the bottle) — remove it.  Environmental sources have location ==
    # the room itself; those should not be depleted.
    container = prso.location
    if container.location == player or container == player:
        _.remove(prso)

print("Thank you very much. I was rather thirsty (from all this talking,")
print("probably).")
