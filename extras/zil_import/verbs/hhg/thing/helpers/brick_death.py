#!moo verb brick_death --on "Thing" --dspec this
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Hand-written BRICK-DEATH replacement.

The auto-translated ZIL body wraps an interactive READ loop in
``while True:`` to handle the canonical 3-press "press ENTER to be
declared dead, then taken to the mortuary" sequence.  DjangoMOO has no
synchronous READ primitive, so the translator emits ``return True``
inside the loop body — exiting BRICK-DEATH before MAKE-WAY-FOR / FINISH
ever runs.  The visible bug: I-BULLDOZER's BULLDOZER-PILES message
prints but the player is never killed / respawned.

This replacement skips the interactive press-ENTER ceremony entirely and
goes straight to MAKE-WAY-FOR + FINISH, which routes through JIGS-UP for
the canonical respawn-or-end-game decision.
"""

from moo.sdk import context

print(
    "Your home collapses in a cloud of dust, and a stray flying brick hits you\n"
    "squarely on the back of the head. You try to think of some suitable last words,\n"
    "but what with the confusion of the moment and the spinning of your head, you\n"
    "are unable to compose anything pithy and expire in silence."
)
# The canonical ZIL flow runs through DEAD-COUNTER 1 → 2 → 3 with the
# ambulance / mortuary patter on each press.  Collapse it to the
# end-state: deliver the mortuary line, then call FINISH which routes
# through JIGS-UP for the respawn.
print()
print(
    "You keep out of this, you're dead and should be concentrating on developing\n"
    "a good firm rigor mortis.  As the ambulance reaches the mortuary..."
)
if _.thing.has_verb("make_way_for"):
    _.thing.make_way_for()
return _.thing.finish()
