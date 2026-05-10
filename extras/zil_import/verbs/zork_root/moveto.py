#!moo verb moveto --on "Zork Root"
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Relocate an object — ZIL ``<MOVE OBJ DEST>`` equivalent.

args[0] = destination

Defined on Zork Root so every Zork Object inherits it; translated routines
invoke as ``obj.moveto(dest)`` (mirroring the default DjangoMOO convention).

Note: we don't reuse ``move`` because the Zork syntax pass emits a ``move``
player command (V-MOVE: "Moving the X reveals nothing.") on $player, which
would shadow this helper through inheritance.
"""

this.location = args[0]
this.save()
