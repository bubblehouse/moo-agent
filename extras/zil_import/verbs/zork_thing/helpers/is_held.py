#!moo verb is_held --on $zork_thing
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Bounded walk-up-location predicate — replaces the translated body of ZIL
``HELD?``.

The translated routine emits ``while True: can = can.location`` and only
exits when ``can`` becomes None or equals the player.  If the location
chain ever cycles or self-loops the worker hangs.  This SDK version
guards against both with a visited-set and a depth bound.

Called as ``_.zork_thing.is_held(obj)``.  ``HELD?`` is in
``_SKIP_ROUTINES`` so the translated body is never emitted.
"""

from moo.sdk import context

obj = args[0] if args else None
if obj is None:
    return False

player = context.player
# Plain assignment (no annotation) — RestrictedPython rejects AnnAssign.
seen = set()
node = obj.location
depth = 0
while node is not None and depth < 64:
    if node == player:
        return True
    if node.pk in seen:
        return False
    seen.add(node.pk)
    node = node.location
    depth += 1
return False
