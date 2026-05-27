#!moo verb score_update score_max --on "System Object"
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Score helpers used by translated ZIL combat / scoring.

``score_update``: adds points to the player's Zork score and returns
the delta unchanged so it can sit inside arithmetic expressions
(``,STRENGTH-MIN + <SCORE-UPDATE ...>``).  Score is stored per-player
as ``zstate_score``.

``score_max``: random integer in ``[1, max(1, n)]`` — stand-in for the
ZIL ``<RANDOM>`` primitive when the translator emits ``score_max`` for
an unrecognized atom.

:param args[0]: ``score_update`` — integer delta to add;
    ``score_max`` — upper-bound integer ``n``.
:returns: ``score_update`` — the same delta;
    ``score_max`` — a random ``int`` in ``[1, max(1, n)]``.
"""

import random
from moo.sdk import context, NoSuchPropertyError

if verb_name == "score_max":
    n = args[0] if args else 1
    return random.randint(1, max(1, int(n)))

try:
    score = context.player.get_property("zstate_score")
except NoSuchPropertyError:
    score = 0
delta = args[0] if args else 0
context.player.set_property("zstate_score", score + delta)
return delta
