#!moo verb is_held --on $thing
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Bounded walk-up-location predicate — replaces the translated body of ZIL
``HELD?``.

The translated routine emits ``while True: can = can.location`` and only
exits when ``can`` becomes None or equals the target.  If the location
chain ever cycles or self-loops the worker hangs.  This SDK version
guards against both with a visited-set and a depth bound.

Two arities, both used by the translated bodies:

- ``_.thing.is_held(obj)`` — "is obj held by player?" Walks
  obj's location chain looking for ``context.player``.  Used by V-PUT,
  V-DROP, etc. (Zork's HELD? semantics with the default ``CONT = WINNER``.)
- ``_.thing.is_held(obj, container)`` — "is obj somewhere inside
  container?" Walks obj's chain looking for ``container``.  Used by
  HHG's PRE-PUT to reject ``put gown in pocket`` (where the pocket is
  on the gown — putting the gown inside its own contents would create
  a containment cycle).

``HELD?`` is in ``_SKIP_ROUTINES`` so the translated body is never
emitted.
"""

from moo.sdk import context

obj = args[0] if args else None
container = args[1] if len(args) > 1 else None
# ZIL globals that hold "an object or <>" translate to an Object or the
# bool ``False`` (an unset slot, e.g. ``,BROWNIAN-SOURCE``).  Z-machine
# ``HELD?`` on the null object is a safe "not held"; mirror that instead
# of walking ``.location`` on a bool.
if obj is None or isinstance(obj, bool):
    return False

target = container if container is not None else context.player
# Plain assignment (no annotation) — RestrictedPython rejects AnnAssign.
seen = set()
node = obj.location
depth = 0
while node is not None and depth < 64:
    if node == target:
        return True
    if node.pk in seen:
        return False
    seen.add(node.pk)
    node = node.location
    depth += 1
return False
