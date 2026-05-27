#!moo verb current_vehicle --on "System Object"
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Return the player's current vehicle (None when not in one).

A vehicle is the player's location when that location's ``vehicle``
property is truthy (boats and the like).  Used by both ``movement.goto``
and ``exit.move`` to relocate the entire vehicle when the player
moves rather than ejecting them onto the floor.

:returns: The vehicle Object, or ``None``.
"""

from moo.sdk import context, NoSuchPropertyError

loc = context.player.location
if loc is None:
    return None
try:
    is_veh = loc.get_property("vehicle")
except NoSuchPropertyError:
    is_veh = False
return loc if is_veh else None
