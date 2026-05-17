#!moo verb say --on "Zork Actor NPC"
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
NPC-side speech helper. Method-call only — invoke as
``npc.say("ho ho ho")`` from inside ``act`` (or any verb running with
the NPC's perspective).

Announces ``<NPC name>: <message>`` to every other occupant of the
NPC's current room. No-op when the NPC is in the void.

The parser ``say`` command on player input dispatches via a different
matching path (``--dspec`` lookup against the player's location) so this
method-call verb won't collide with player ``say`` invocations.
"""

if not args:
    return
message = args[0]
room = this.location
if room is None:
    return
room.announce_all_but(this, f"{this.name}: {message}")
