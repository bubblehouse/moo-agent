#!moo verb this_is_it --on "Thing" --dspec this
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Set the parser "it" pronoun to OBJ — ZIL ``THIS-IS-IT`` (``<SETG P-IT-OBJECT .OBJ>``).

Lives in the shared substrate because ``print_contents`` and ``put`` call
``_.thing.this_is_it(...)``, but the routine is defined only in the
zork-substrate — HHG's ZIL has no ``THIS-IS-IT``, so its Thing lacked the
verb and those calls raised ``AttributeError`` (surfaced as the
intermittent ``open panel`` crash in the Galley, where V-OPEN reveals the
Nutrimat's contents through ``print_contents``).  The hand-written copy is
shared by both games and supersedes Zork's generated emission via
``handwritten_paths``; its body is identical to that generated routine.

:param args[0]: The object that "it" should now refer to.
:returns: The stored object.
"""

from moo.sdk import context

obj = args[0] if args else None
return context.player.zstate_set("P-IT-OBJECT", obj)
