#!moo verb pre_drop --on "Thing" --dspec this
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Hand-written PRE-DROP replacement.

Adds a self-reference branch to the auto-translated body: when the
player tries to ``drop me``, the canonical Zork response is "You'd lose
your balance." not the substrate's "You're not carrying the Wizard."
(where ``Wizard`` is the SSH username leaked via ``self.desc()``).

Preserves the canonical disembark-when-dropping-the-current-room
behavior the auto-translator generates.
"""

from moo.sdk import NoSuchObjectError, context

parser = context.parser
player = context.player

try:
    prso = parser.get_dobj() if parser.has_dobj_str() else None
except NoSuchObjectError:
    prso = None

if prso is None:
    if parser is not None and parser.has_dobj_str():
        print("There is no '" + parser.dobj_str + "' here.")
    else:
        print("I don't know how to do that.")
    return True

if prso == player:
    print("You'd lose your balance.")
    return True

if prso == player.location:
    _.perform("disembark", prso, None)
    return True
