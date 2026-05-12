#!moo verb examine describe what whats x --on "Zork Thing" --dspec this
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Hand-written V-EXAMINE replacement.

The auto-emitted body interpolates ``prso.desc()`` into the canonical
"There's nothing special about the X." line, which leaks the SSH
username when the player examines themselves (``examine me``).
Adds a ``prso == player`` short-circuit before the canonical
text / contbit / desc dispatch.
"""

from moo.sdk import NoSuchObjectError, context

player = context.player
parser = context.parser

try:
    prso = parser.get_dobj() if parser.has_dobj_str() else None
except NoSuchObjectError:
    prso = None

if prso is None:
    if parser is not None and parser.has_dobj_str():
        print("There is no '" + parser.dobj_str + "' here.")
    else:
        print("What do you want to examine?")
    return

if prso == player:
    print("There's nothing special about yourself.")
    return

if prso.getp("text"):
    print(prso.getp("text"))
    return

if prso.flag("contbit") or prso.flag("is_door"):
    return _.zork_thing.look_inside()

print("There's nothing special about the " + prso.desc() + ".")
return
