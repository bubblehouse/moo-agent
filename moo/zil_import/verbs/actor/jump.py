#!moo verb jump leap dive --on "Actor"
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Stub for V-LEAP / JUMP.  The canonical V-LEAP body walks the Z-machine
exit table to look for a fall-through direction; the translator skips
it (in ``_SKIP_ROUTINES``).  Bare ``jump`` should print canonical
"Wheeeeeeeeee!!!!!" rather than "I don't know how to do that".

``dive`` is the third arm of ``<SYNONYM JUMP LEAP DIVE>`` (both games).
Without it here, bare ``dive`` falls through to the compound JUMP
dispatcher, whose only fall-through is V-THROUGH (the bare V-LEAP arm
is skipped), so the player gets the ungrammatical "What do you want to
through?" prompt instead of the canonical Wheeee.  Listing ``dive``
makes it symmetric with ``jump``/``leap``.
"""

print("Wheeeeeeeeee!!!!!")
