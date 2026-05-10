#!moo verb here --on "Zork Actor"
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Effective room for the player — ZIL ``HERE`` global.

When the player is standing inside a vehicle (e.g. the magic boat), ZIL
``HERE`` returns the room the vehicle is in, not the vehicle itself.
This mirrors that semantic so river-room daemons, ``go east`` etc. see
the river room rather than the boat.

Called as ``context.player.here()`` (or ``player.here()`` after hoist).
"""

from moo.sdk import NoSuchPropertyError

loc = this.location
if loc is None:
    return None
try:
    is_vehicle = loc.get_property("vehicle")
except NoSuchPropertyError:
    is_vehicle = False
return loc.location if is_vehicle else loc
