#!moo verb other_side --on "Thing" --dspec this
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Hand-written OTHER-SIDE replacement.

The auto-emitted body walks the Z-machine direction property table via
``nextp`` + ``getpt`` + ``ptsize`` to find the exit that uses ``args[0]``
as its DOOR property.  DjangoMOO has no direction property table — the
``nextp`` call NameErrors at runtime, crashing every ``enter <door>`` on
a door that V-THROUGH dispatches against.

Replace the table walk with a direct exit search: scan the player's
room's ``exits`` list for one whose ``door`` property matches the
argument; return that exit's direction alias (matching the canonical
ZIL return shape: a direction property number suitable for V-WALK).

If no exit references this door, return False so V-THROUGH falls
through to the canonical "you hit your head" / "contortion" branches.

Both callers (V-THROUGH and V-OUT-OF) only check truthiness of the
return value before passing it to ``walk``, so returning the direction
string is a valid substitute for the ZIL direction-property integer.
"""

from moo.sdk import NoSuchPropertyError, context

player = context.player
door = args[0] if args else None
if door is None:
    return False

here = player.here()
if here is None:
    return False

try:
    exits = here.get_property("exits") or []
except NoSuchPropertyError:
    exits = []

for cand in exits:
    try:
        cand_door = cand.get_property("door")
    except NoSuchPropertyError:
        cand_door = None
    if cand_door is not None and cand_door == door:
        first_alias = cand.aliases.values_list("alias", flat=True).first()
        return first_alias or cand.name
return False
