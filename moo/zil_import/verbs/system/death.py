#!moo verb jigs_up --on "System Object"
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Kill the player: print death message and respawn at starting room.

The starting room is read from ``this.player_start`` (stored on the
System Object as world config).

:param args[0]: Death-message string to print before respawn.
"""

from moo.sdk import context

print(args[0])
start = this.get_property("player_start")
context.player.location = start
context.player.save()
print("\n**** You have died ****\n")
context.player.zstate_set("DEATHS", (context.player.zstate_get("DEATHS") or 0) + 1)
