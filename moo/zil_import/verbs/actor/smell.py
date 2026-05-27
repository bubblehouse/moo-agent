#!moo verb smell sniff --on "Actor"
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Bare-form V-SMELL: when the player types ``smell`` with no dobj, give a
canonical inert response.  The Thing substrate handles ``smell <obj>``;
this stub captures the no-dobj case so it doesn't fall back to "I don't
know how to do that".
"""

print("You smell nothing unexpected.")
