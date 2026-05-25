#!moo verb sit --on "Actor" --dspec either
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Stub for SIT — V-SIT was not in the canonical Zork I dispatcher table,
and ZIL bundled ``sit`` into ``<SYNONYM WALK ...>`` so the parser would
treat it as a movement verb.  In DjangoMOO that routes through the
walk dispatcher and prints "You can't go that way", which is wrong:
canonical Zork prints something inert and gameplay continues.

This stub captures the bare ``sit`` form so it doesn't fall back to
walk.  ``sit on rug`` and similar still go through their own per-object
handlers when defined; this only fires when no dobj-bound match wins.
"""

print("Quaint, but unproductive.")
