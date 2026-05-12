#!moo verb i_bat --on "Zork Thing" --dspec this
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Bat-room daemon — replaces the missing BAT-FUNCTION translation.

Fires every turn while the player is in the Bat Room without garlic.
Calls FLY-ME to relocate the player to a random Coal Mine room — the
classic Zork bat encounter.  Returns False when the daemon is a no-op
this tick so queue.tick doesn't propagate a spurious "handled" flag.
"""

from moo.sdk import context, lookup, NoSuchObjectError

player = context.player

try:
    bat_room = lookup("bat_room")
except NoSuchObjectError:
    return False

# Only fire when the player is actually in the Bat Room.  Even though
# the daemon is recurring=1, queue.tick fires unconditionally; gating
# here keeps it cheap when the player is elsewhere.
if player.here() != bat_room:
    return False


# Garlic in inventory wards off the bat — canonical: "Bat takes one
# whiff and flies away."  Match on alias to cover both the kitchen's
# garlic clove (name "clove of garlic") and any test-only stand-in.
def _carries_garlic(actor):
    for item in actor.contents.all():
        name_lower = (item.name or "").lower()
        if "garlic" in name_lower:
            return True
        for alias in item.aliases.all():
            if "garlic" in (alias.alias or "").lower():
                return True
    return False


if _carries_garlic(player):
    return False

# No garlic — bat picks the player up.  FLY-ME is the canonical ZIL
# routine; route through the substrate so per-game logic stays in one
# place.  fly_me may not exist if the translator skipped it; in that
# case print the canonical bat-grab message and stop.
try:
    return _.zork_thing.fly_me()
except (NoSuchObjectError, AttributeError):
    print("A large vampire bat swoops down and grabs you!")
    return True
