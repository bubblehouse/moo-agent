#!moo verb diagnose --on "Actor" --dspec none
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Hand-written V-DIAGNOSE replacement.

The auto-translated body computes cure time as
``CURE-WAIT * (wd - 1) + <GET ,C-TABLE <- ,C-TICK ...>>``.  The
``C-TABLE`` global is part of the Z-machine clock-interrupt machinery
we replace wholesale with ``zil_sdk/queue_sdk.py``; the translator
emits ``_.table_get(None, ...)`` which returns ``None``, then the
``int + None`` addition raises ``TypeError`` and crashes the verb on
any wounded ``diagnose``.

This replacement keeps the canonical text but drops the C-TABLE
contribution to the cure estimate.  Players see "...cured after N
moves." where N is ``CURE-WAIT * max(wd-1, 0)`` — slightly less
precise than canonical Zork but never crashes.

See [BUGS.md] entry "diagnose while wounded crashes" for the original
trace.
"""

from moo.sdk import context

player = context.player
ms = _.zork_thing.fight_strength(False)
wd = player.getp("strength") or 0
rs = ms + wd

if _.table_get(None, player.zstate_get("C-ENABLED?")) == 0:
    wd = 0
else:
    wd = -wd

if wd == 0:
    print("You are in perfect health.", end="")
else:
    print("You have ", end="")
    if wd == 1:
        print("a light wound,", end="")
    elif wd == 2:
        print("a serious wound,", end="")
    elif wd == 3:
        print("several wounds,", end="")
    elif wd > 3:
        print("serious wounds,", end="")

if wd != 0:
    cure_wait = player.zstate_get("CURE-WAIT") or 0
    cure_time = cure_wait * max(wd - 1, 0)
    print(" which will be cured after " + str(cure_time) + " moves.", end="")

print()
print("You can ", end="")
if rs == 0:
    print("expect death soon", end="")
elif rs == 1:
    print("be killed by one more light wound", end="")
elif rs == 2:
    print("be killed by a serious wound", end="")
elif rs == 3:
    print("survive one serious wound", end="")
elif rs > 3:
    print("survive several wounds", end="")
print(".")

deaths = player.zstate_get("DEATHS") or 0
if deaths != 0:
    print("You have been killed ", end="")
    if deaths == 1:
        print("once", end="")
    else:
        print("twice", end="")
    print(".")
