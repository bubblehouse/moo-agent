#!moo verb eat consume taste bite --on "Thing" --dspec this
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Hand-written V-EAT replacement.

The auto-emitted body falls through to ``prso.desc()`` for self-target
inputs, leaking the SSH username (e.g. ``the Wizard``) into the
no-edible-here refusal.  Adds a ``prso == player`` short-circuit before
the canonical edible / drinkable branches.
"""

from moo.sdk import NoSuchObjectError, context, lookup

player = context.player
parser = context.parser

try:
    prso = parser.get_dobj() if parser.has_dobj_str() else None
except NoSuchObjectError:
    prso = None
the_player_verb = parser.words[0].lower() if context.parser is not None and parser.words else verb_name

if prso is None:
    if parser is not None and parser.has_dobj_str():
        print("There is no '" + parser.dobj_str + "' here.")
    else:
        print("What do you want to eat?")
    return

if prso == player:
    print("Auto-cannibalism is not the answer.")
    return

if prso.flag("edible"):
    if not prso.location == player and not prso.location.location == player:
        print("You're not holding that.")
    elif the_player_verb == "drink":
        print("How can you drink that?", end="")
    else:
        print("Thank you very much. It really hit the spot.", end="")
        _.remove(prso)
    print()
    return

if prso.flag("drinkable"):
    nobj = prso.location
    if (
        prso.location == lookup("global_objects")
        or lookup("global_water").global_in(player.here())
        or prso == lookup("pseudo_object")
    ):
        return _.thing.hit_spot()
    if not nobj or not _.thing.is_accessible(nobj):
        print("There isn't any water here.")
        return
    if _.thing.is_accessible(nobj) and not nobj.location == player:
        print("You have to be holding the " + nobj.desc() + " first.")
        return
    if not nobj.flag("open"):
        print("You'll have to open the " + nobj.desc() + " first.")
        return
    return _.thing.hit_spot()

print("I don't think that the " + prso.desc() + " would agree with you.")
return
