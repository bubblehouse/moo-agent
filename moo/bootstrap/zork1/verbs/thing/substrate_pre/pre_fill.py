#!moo verb pre_fill --on "Thing" --dspec this
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Hand-written PRE-FILL replacement.

The auto-emitted body walks the room's property table via Z-machine
``getpt(here, P?GLOBAL)`` + ``ptsize`` to discover whether a global water
source is in scope.  DjangoMOO doesn't have that table — the call
NameErrors at runtime, crashing any bare ``fill <bottle>`` or ``fill
<bottle> with water`` from a non-water-source room.

Replace the table walk with a direct lookup: if the player's room has a
``water_source`` flag set (or sits adjacent to GLOBAL-WATER as recorded
in the room's ``global_objects`` list), allow auto-fill with global
water.  Otherwise fall back to the canonical "There is nothing to fill
it with." refusal.

iobj-present branch is preserved: explicit ``fill X with water`` returns
False so the substrate's ``You may know how to do that, but I don't.``
fires; ``fill X with <other>`` rewrites to ``put <other> in X``.
"""

from moo.sdk import NoSuchObjectError, NoSuchPropertyError, context, lookup

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

try:
    global_water = lookup("global_water")
except NoSuchObjectError:
    global_water = None
try:
    water = lookup("water")
except NoSuchObjectError:
    water = None

if prso is None:
    if parser is not None and parser.has_dobj_str():
        print("There is no '" + parser.dobj_str + "' here.")
    else:
        print("I don't know how to do that.")
    return True

if prsi is None:
    # Bare ``fill <bottle>`` — auto-discover the water source.
    here = player.here()
    water_in_scope = False
    if here is not None:
        try:
            globals_here = here.get_property("global_objects") or []
        except NoSuchPropertyError:
            globals_here = []
        if global_water is not None and global_water in globals_here:
            water_in_scope = True
        if not water_in_scope and here.flag("water_source"):
            water_in_scope = True
    if water_in_scope and global_water is not None:
        _.perform("fill", prso, global_water)
        return True
    if water is not None and water.location == player.location:
        _.perform("fill", prso, water)
        return True
    print("There is nothing to fill it with.")
    return True

if water is not None and prsi == water:
    # Let the substrate decide ("You may know how to do that, but I don't.").
    return False
if global_water is not None and prsi == global_water:
    return False
# Filling with something other than water → rewrite to ``put X in <bottle>``.
_.perform("put", prsi, prso)
return True
