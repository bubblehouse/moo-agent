#!moo verb listen --on "Actor"
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Bare-form V-LISTEN: when the player types ``listen`` with no dobj, give
a canonical inert response.  The Thing substrate handles
``listen <obj>``; this stub captures the no-dobj case.
"""

print("You hear nothing unexpected.")
