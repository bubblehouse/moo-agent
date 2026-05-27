#!moo verb dig --on "Thing" --dspec this
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
HHG V-DIG — pick a random "wasted effort" rebuke from the WASTES table.

Canonical ZIL is ``<TELL <PICK-ONE ,WASTES> CR>``.  Replaces the
Zork-specific hand-written dig.py (which checks shovel / toolbit /
``Digging with X is silly``) — those messages reference Zork tools the
HHG bootstrap doesn't seed, and V-BLOCK / V-WAVE-AT chains land here
via ``<V-DIG>``.  Without this file HHG ``lie before bulldozer`` →
V-BLOCK → V-DIG would print "Digging with a bulldozer is silly."
(bulldozer is the iobj after the dispatcher routed the prep).
"""

from moo.sdk import context

player = context.player
print(_.pick(player.zstate_get("WASTES")))
return True
