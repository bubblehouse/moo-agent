#!moo verb pre_sgive --on "Zork Thing" --dspec this
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Hand-written PRE-SGIVE replacement.

The auto-translator emits ``_.perform("give", prsi, prso)`` unconditionally,
which re-enters the give dispatcher and recurses without bound when the
indirect object is the player (``give sack to me``). The recursion
RecursionErrors out and leaks a Python traceback to the player.

Adds a self-target short-circuit before the perform call, mirroring the
existing guards in ``substrate_pre/pre_drop.py`` and
``substrate_verbs/attack.py``.
"""

from moo.sdk import NoSuchObjectError, context

parser = context.parser
player = context.player

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
        print("I don't know how to do that.")
    return True

if prsi == player:
    print("You can't give something to yourself.")
    return True

_.perform("give", prsi, prso)
return True
