#!moo verb i_announcement --on "Thing" --dspec this
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
I-ANNOUNCEMENT (HHG override) — the Vogon captain's shipboard intercom.

Body mirrors the generated routine, with ONE addition: don't re-arm if a
mid-tick DISABLE already tombstoned us.  Canonically I-GUARDS
``<DISABLE>``\\ s I-ANNOUNCEMENT when it drags you out of the Hold, but in
this port the disable races the top-of-body self-re-arm: I-ANNOUNCEMENT
re-appends itself to the queue tail every turn, so when both are due in
the same tick and I-GUARDS is processed first, its ``_.cancel`` lands and
then I-ANNOUNCEMENT fires and re-adds itself — the ``zstate_drop``
tombstone only suppresses the queue's *auto*-re-queue, not this explicit
``_.queue``.  Without the guard the intercom follows you onto the Heart of
Gold forever (BUGS.md).

Scoped to this one daemon on purpose: a clock-level "DISABLE wins
same-tick" fix in the shared ``queue.py`` breaks the Vogon cascade (the
act's daemons cancel + re-queue each other across one tick in a precise
order).  See references/rule-zero.md.
"""

from moo.sdk import context, lookup, NoSuchPropertyError

player = context.player

try:
    dropped = context.player.get_property("zstate_drop") or []
except NoSuchPropertyError:
    dropped = []
if "i-announcement" in dropped:
    # I-GUARDS DISABLEd us earlier this same tick — stay dead, don't re-arm.
    return False

_.queue("i-announcement", -1)
print("An announcement is coming over the ship's intercom. \"")
if _.thing.is_held(lookup("babel_fish"), player):
    print(
        "This is the Captain. My instruments show that we've picked up a couple of\nhitchhikers. I hate freeloaders, and when my guards find you I'll have you\nthrown into space. On second thought, maybe I'll read you some of my poetry\nfirst. Repeating...\""
    )
    return True
else:
    print("E", end="")
    # ZIL: <PRODUCE-GIBBERISH ...>
    _.thing.produce_gibberish(10)
    print()
    return True
