#!moo verb sing --on "Actor"
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Stub for V-SING / V-DANCE.  Canonical Zork I prints something inert and
returns; the routine isn't generated cleanly because it doesn't carry
useful state.  Captures the bare ``sing`` form so it doesn't fall back
to "I don't know how to do that".
"""

print("Your singing is enough to scare away a pack of wolves.")
