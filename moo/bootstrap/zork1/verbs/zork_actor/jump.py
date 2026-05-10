#!moo verb jump leap --on "Zork Actor"
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Stub for V-LEAP / JUMP.  The canonical V-LEAP body walks the Z-machine
exit table to look for a fall-through direction; the translator skips
it (in ``_SKIP_ROUTINES``).  Bare ``jump`` should print canonical
"Wheeeeeeeeee!!!!!" rather than "I don't know how to do that".
"""

print("Wheeeeeeeeee!!!!!")
