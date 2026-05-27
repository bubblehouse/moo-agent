#!moo verb look_inside --on "Thing" --dspec this
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Hand-written V-LOOK-INSIDE replacement.

The auto-emitted body formats the non-container refusal as
``"You can't look inside a " + prso.desc() + "."``, which produces
"You can't look inside a sand." (mass noun mis-articled) for ``look in
sand``.  Switching to "the" matches canonical Zork ("You can't look
inside the sand.") and avoids the article-agreement problem entirely
for mass and proper nouns.
"""

from moo.sdk import NoSuchObjectError, context

parser = context.parser
try:
    prso = parser.get_dobj() if parser.has_dobj_str() else None
except NoSuchObjectError:
    prso = None

if prso is None:
    if parser is not None and parser.has_dobj_str():
        print("There is no '" + parser.dobj_str + "' here.")
    else:
        print("What do you want to look inside?")
    return

if prso.flag("is_door"):
    if prso.flag("open"):
        print("The " + prso.desc() + " is open, but I can't tell what's beyond it.")
    else:
        print("The " + prso.desc() + " is closed.")
    return

if prso.flag("contbit"):
    if prso.flag("actorbit"):
        print("There is nothing special to be seen.")
        return
    if _.thing.is_see_inside(prso):
        if prso.contents.first() and _.thing.print_cont(prso):
            return True
        if _.thing.null_f():
            return True
        print("The " + prso.desc() + " is empty.")
        return
    print("The " + prso.desc() + " is closed.")
    return

print("You can't look inside the " + prso.desc() + ".")
