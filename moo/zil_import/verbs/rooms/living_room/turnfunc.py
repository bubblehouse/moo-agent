#!moo verb turnfunc --on "Living Room" --dspec either
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Hand-written LIVING-ROOM-FCN M-END replacement.

The auto-translator's emission dereferences ``prso.location`` without a
null guard, so any bare verb (``take``, ``put``, ``pick``) in the Living
Room AttributeErrors and leaks a Python traceback to the player.

Mirrors the auto-translated body but skips the ``prso.location`` branch
when ``prso`` is None — the score update still fires unconditionally so
deposits into the trophy case credit correctly.
"""

from moo.sdk import NoSuchObjectError, context, lookup

player = context.player
parser = context.parser

try:
    prso = parser.get_dobj() if parser.has_dobj_str() else None
except NoSuchObjectError:
    prso = None
try:
    prsi = parser.get_iobj() if parser.has_iobj() else None
except NoSuchObjectError:
    prsi = None

trophy_case = lookup("trophy_case")
the_player_verb = (
    args[1]
    if len(args) > 1
    else (parser.words[0].lower() if context.parser is not None and parser.words else verb_name)
)

if the_player_verb in ["take", "get", "pick"] or (
    the_player_verb in ["put", "place", "insert"] and prsi == trophy_case
):
    if prso is not None and prso.location == trophy_case:
        _.thing.touch_all(prso)
    player.zstate_set("SCORE", (player.zstate_get("BASE-SCORE") + _.thing.otval_frob()))
    _.thing.score_upd(0)
    return False
