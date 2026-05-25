#!moo verb i_thief --on "Thing" --dspec this
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Smart-thief daemon — replaces the auto-translation.

Canonical ZIL I-THIEF random-walks ~110 RLANDBIT rooms; reaching
TREASURE-ROOM to fire DEPOSIT-BOOTY (which OPENs the egg) takes
~50-100 turns.  This template keeps the canonical encounter/steal/rob
helpers but adds two deterministic bridges: once the thief has loot,
beeline straight to TREASURE-ROOM; after deposit, retreat to a random
outdoor room.

:returns: Truthy when a player-visible event happened this tick.
"""

import random
from moo.sdk import context, lookup, NoSuchObjectError, NoSuchPropertyError

player = context.player
thief = lookup("thief")
treasure_room = lookup("treasure_room")
stiletto = lookup("stiletto")
large_bag = lookup("large_bag")


def has_treasure_loot():
    """
    True when the thief is carrying anything other than its own gear.

    :returns: ``True`` when at least one carried item has positive ``tvalue``.
    """
    for item in thief.contents.all():
        if item == stiletto or item == large_bag:
            continue
        try:
            if item.getp("tvalue") > 0:
                return True
        except NoSuchPropertyError:
            pass
    return False


rm = thief.location
here_p = not thief.flag("invisible")
flg = False

# Smart-thief bridge: with loot, beeline to Treasure Room and deposit next tick.
has_loot = has_treasure_loot()

if has_loot and rm != treasure_room:
    # Move silently — player never sees the thief in transit.
    thief.moveto(treasure_room)
    thief.set_flag("invisible", True)
    rm = treasure_room
    here_p = False

# In TREASURE-ROOM without the player → HACK-TREASURES + DEPOSIT-BOOTY (sets OPENBIT on egg).
if rm == treasure_room and rm != player.here():
    if here_p:
        _.thing.hack_treasures()
        here_p = False
    _.thing.deposit_booty(treasure_room)
    flg = True
elif rm == player.here() and rm.flag("dark") and lookup("troll").location != player.here():
    # Encounter — thief only meets player in dark (non-ONBIT) rooms.
    if _.thing.thief_vs_adventurer(here_p):
        return True
    if thief.flag("invisible"):
        here_p = False
else:
    if thief.location == rm and not thief.flag("invisible"):
        thief.set_flag("invisible", True)
        here_p = False
    if rm.flag("touchbit"):
        _.thing.rob(rm, thief, 75)
        if rm.flag("maze") and player.here().flag("maze"):
            flg = _.thing.rob_maze(rm) or flg
        else:
            flg = _.thing.steal_junk(rm) or flg

# Re-check loot after this tick's encounter / rob.
if not has_loot:
    has_loot = has_treasure_loot()

if not here_p:
    # Recover the stiletto (canonical post-tick) and advance one room in the cycle.
    _.thing.recover_stiletto()
    if not has_loot:
        # The "outdoor non-sacred" room set is static after bootstrap, so we
        # cache the PK cycle on the System Object the first time we need it.
        # Walking 110 children with two .flag() verb dispatches each runs to
        # ~220 invocations per tick, which blows past the 15s celery hard
        # limit under load.  Cached PKs reduce the steady-state work to a
        # single property read + numeric index + lookup-by-pk.
        sysobj = lookup("System Object")
        try:
            candidate_pks = sysobj.get_property("_thief_walk_pks")
        except NoSuchPropertyError:
            candidate_pks = None
        if not candidate_pks:
            try:
                room_class = lookup("Room")
            except NoSuchObjectError:
                room_class = None
            if room_class is not None:
                ordered = list(room_class.children.filter(name__isnull=False).order_by("pk"))
                candidate_pks = [r.pk for r in ordered if r.flag("outdoor") and not r.flag("sacred")]
                sysobj.set_property("_thief_walk_pks", candidate_pks)
        if candidate_pks:
            # Pick next room in the cycle, wrapping at the end.
            cur_idx = candidate_pks.index(rm.pk) if rm.pk in candidate_pks else -1
            target_pk = candidate_pks[(cur_idx + 1) % len(candidate_pks)]
            target = lookup(target_pk)
            thief.moveto(target)
            thief.set_flag("hostile", False)
            thief.set_flag("invisible", True)
            player.zstate_set("THIEF-HERE", False)
return flg
