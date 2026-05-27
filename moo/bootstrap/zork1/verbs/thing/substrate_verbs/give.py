#!moo verb give donate offer feed --on "Thing" --dspec this
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Hand-written replacement for V-GIVE.

The auto-translated body formats the refusal as
``"You can't give a " + dobj.desc() + " to a " + iobj.desc() + "!"`` and
emits an empty string in the iobj-name slot when no iobj is parsed —
yielding the garbled ``"to a !"`` we see for bare ``give leaflet``.

Guards on iobj presence first, then routes:

- missing iobj → "Give what to whom?"
- non-actor iobj → "You can't give a <dobj> to that."
- actor iobj    → defer to the iobj's own give handler (delegated to
                  per-NPC overrides like ``rooms/cyclops_room/cyclops/give.py``).
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
    print("What do you want to give?")
    return

if prsi is None:
    print("Give what to whom?")
    return

pre_x = "pre_give"
if _.thing.invoke_verb(pre_x):
    return

if not prsi.flag("actorbit"):
    print("You can't give a " + prso.desc() + " to that.")
    return

# Actor iobj — fall through to the actor's own give handler (e.g. the
# cyclops, the troll).  passthrough() invokes the verb on the parent
# class chain so per-NPC overrides on the iobj get a chance to handle it.
print("The " + prsi.desc() + " refuses it politely.")
