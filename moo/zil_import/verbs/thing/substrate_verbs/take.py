#!moo verb take get hold carry remove grab catch pick --on "Thing" --dspec this
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Hand-written V-TAKE replacement.

The auto-emitted body invokes ``pre_take`` on the Thing class
(``_.thing.invoke_verb("pre_take")``) — that always dispatches to
the substrate ``pre_take`` and never reaches any per-object override.
Canonical Zork relies on per-object ACTION-FCN gating; in our
translation, per-object overrides land as ``pre_take`` verbs on the
specific object (e.g. ``pot of gold``'s rainbow-flag gate).

Dispatch order: per-object ``pre_take`` (if any), then substrate
``pre_take``, then the standard ITAKE move + "Taken." print.
"""

from moo.sdk import NoSuchObjectError, context

parser = context.parser
try:
    prso = parser.get_dobj() if parser.has_dobj_str() else None
except NoSuchObjectError:
    prso = None

if prso is None:
    if context.parser is not None and context.parser.has_dobj_str():
        print("There is no '" + context.parser.dobj_str + "' here.")
    else:
        print("What do you want to take?")
    return

# Per-object pre_take override — pot of gold's RAINBOW-FLAG gate, etc.
if prso.has_verb("pre_take", recurse=False) and prso.invoke_verb("pre_take"):
    return
# Substrate pre_take handles the generic CONTBIT / WEARBIT / IN-PLAYER cases.
if _.thing.invoke_verb("pre_take"):
    return
if _.thing.itake() is True:
    # Clear the invisible flag the thief's STEAL-JUNK sets on items it
    # bags.  Canonical ZIL only clears invisible during a TREASURE-ROOM
    # drop or a reset; without this clear, items the thief snatched and
    # later released stay invisible forever and ``take <obj>`` reports
    # "Taken." but the dobj never appears in inventory.  Also covers the
    # post-troll-death axe (STEAL-JUNK set invisible before the troll
    # died, leaving the axe untakeable).
    if prso.has_property("invisible") and prso.flag("invisible"):
        prso.set_flag("invisible", False)
    if prso.flag("wearbit") if prso else None:
        print("You are now wearing the " + (prso.desc() if prso else "") + ".")
        return
    else:
        print("Taken.")
        return
