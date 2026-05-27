#!moo verb idrop --on "Thing" --dspec this
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Hand-written IDROP replacement for HHG.

The auto-translated body returns ``None`` after printing a rejection
message (the canonical ZIL ``<TELL ... CR>`` pattern with no explicit
``<RTRUE>``).  ZIL's COND-arm-implicit-return is truthy when the arm
prints, but the translator's ``_fix_return_print`` lowers
``return print(...)`` to ``print(...)\nreturn`` (which yields None).
Callers like PRE-THROW / PRE-DROP / PRE-GIVE / PRE-PUT use
``(<IDROP> <RTRUE>)`` to short-circuit when IDROP handled the input.
With None return, PRE-X falls through and V-THROW prints "You missed."
on top of "you don't even have <obj>."

This file enforces the canonical "printed → handled" return for HHG's
IDROP branches.  Reasons IDROP rejects:

* PRSO not in inventory (``"That's easy for you to say…"``)
* PRSO is inside a closed container (``"Impossible because…"``)
* PRSO is worn / babel-fish (``"You'll have to remove it first."``)
"""

from moo.sdk import context, invoked_verb_name, lookup

parser = context.parser
player = context.player

if not parser.has_dobj_str():
    return False
try:
    prso = parser.get_dobj()
except Exception:  # pylint: disable=broad-exception-caught
    return False
try:
    prsi = parser.get_iobj() if parser.has_iobj() else None
except Exception:  # pylint: disable=broad-exception-caught
    prsi = None

the_player_verb = invoked_verb_name(verb_name)

# Pass-through cases — IDROP says "fine, continue" by returning False.
if prso == lookup("hangover"):
    return False
if prso == lookup("no_tea") and player.zstate_get("HOLDING-NO-TEA"):
    return False
if prso in (lookup("dangly_bit"), lookup("large_plug"), lookup("small_plug")) and the_player_verb in (
    "put",
    "place",
    "insert",
    "put-on",
):
    return False
if the_player_verb == "give" and prso == lookup("speech"):
    return False
if prso == lookup("sleeves"):
    return _.thing.dig()
if prso in (lookup("eyes"), lookup("ears"), lookup("hands"), lookup("head")):
    if the_player_verb in ("drop", "throw", "toss", "give"):
        return _.thing.count()
    if the_player_verb == "put-on" and prsi == lookup("satchel"):
        return _.thing.count()
    return False
if prso == lookup("spare_drive") and prsi in (
    lookup("large_receptacle"),
    lookup("small_receptacle"),
    lookup("controls"),
    lookup("plotter"),
):
    return False

# Rejection cases — print the canonical message and return True so the
# caller's ``<IDROP>`` test in PRE-X short-circuits to RTRUE.
if not _.thing.is_held(prso):
    print("That's easy for you to say since you don't even have" + _.thing.article(prso, True) + ".")
    return True
if prso == lookup("plant"):
    _.perform("drop", lookup("flowerpot"), None)
    return True
if prso.flag("integralbit"):
    return _.thing.part_of()
loc_obj = prso.location
if loc_obj is not None and loc_obj != player and loc_obj.flag("contbit") and not loc_obj.flag("open"):
    print("Impossible because" + _.thing.article(loc_obj, True) + " is closed.")
    return True
if (prso == lookup("babel_fish") and the_player_verb != "show") or prso.flag("wornbit"):
    print("You'll have to remove it first.")
    return True

return False
