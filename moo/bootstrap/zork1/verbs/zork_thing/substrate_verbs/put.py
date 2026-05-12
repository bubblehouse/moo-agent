#!moo verb put apply stuff insert place hide --on "Zork Thing" --dspec this
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Hand-written V-PUT replacement.

The auto-emitted body collapses three distinct iobj-rejection cases
into one ``"You can't do that."`` line:

1.  iobj string was given but unresolved (``put map in mailbox`` when
    mailbox isn't in scope) — should say "There is no 'mailbox' here."
2.  iobj is openable + closed (``put bar in case`` when the trophy case
    is closed) — should say "The trophy case is closed."
3.  iobj is genuinely not a container — keeps the "You can't do that."
    fallback.

This rewrite preserves the canonical weight / capacity / move logic
unchanged; only the iobj-rejection ladder gets the missing branches.
"""

from moo.sdk import NoSuchObjectError, context

parser = context.parser

try:
    prso = parser.get_dobj() if parser.has_dobj_str() else None
except NoSuchObjectError:
    prso = None
try:
    prsi = parser.get_iobj() if parser.has_iobj() else None
except NoSuchObjectError:
    prsi = None

if prso is None:
    if parser is not None and parser.has_dobj_str():
        print("There is no '" + parser.dobj_str + "' here.")
    else:
        print("What do you want to put?")
    return

if prsi is None:
    # parser.has_iobj() only returns True when the iobj resolved to an
    # Object — useless here.  Walk parser.prepositions directly looking
    # for a record with a non-empty STRING (record[1]) regardless of
    # whether it resolved (record[2]).  An unresolved iobj string means
    # the player named something not in scope ("put map in mailbox" with
    # mailbox out of reach) — echo the canonical "There is no 'X' here."
    iobj_str = ""
    for prep_objects in (parser.prepositions or {}).values():
        for record in prep_objects:
            if len(record) >= 2 and record[1]:
                iobj_str = record[1]
                break
        if iobj_str:
            break
    if iobj_str:
        print("There is no '" + iobj_str + "' here.")
    else:
        print("What do you want to put it in?")
    return

if _.zork_thing.invoke_verb("pre_put"):
    return

# Canonical V-PUT ladder: must be a container OR a vehicle.  If it's
# a container but closed, print the canonical "is closed" message.
# (CONTBIT covers all takeable+non-takeable containers including the
# trophy case; openable is a stricter ZIL flag the trophy case doesn't
# carry.)
if not prsi.flag("contbit") and not prsi.flag("vehicle"):
    print("You can't put things in the " + prsi.desc() + ".")
    return True

if prsi.flag("contbit") and not prsi.flag("open") and not prsi.flag("vehicle"):
    print("The " + prsi.desc() + " is closed.")
    return _.zork_thing.this_is_it(prsi)

if prsi == prso:
    print("How can you do that?")
    return

if prso.location == prsi:
    print("The " + prso.desc() + " is already in the " + prsi.desc() + ".")
    return

if ((_.zork_thing.weight(prsi) + _.zork_thing.weight(prso)) - prsi.getp("size")) > prsi.getp("capacity"):
    print("There's no room.")
    return

if not _.zork_thing.is_held(prso) and prso.flag("trytakebit"):
    print("You don't have the " + prso.desc() + ".")
    return True

if not _.zork_thing.is_held(prso) and not _.zork_thing.itake():
    return True

prso.moveto(prsi)
prso.set_flag("touchbit", True)
_.zork_thing.score_obj(prso)
print("Done.")
return
