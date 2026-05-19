#!moo verb climb sit --on "Zork Actor" --dspec either
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Hand-written CLIMB dispatcher.

The auto-emit unconditionally rewrites ``climb <thing>`` to
``walk("up")``, which inherits the source room's UP-exit failure
message.  In Forest rooms that border the impassable mountains, the
UP-exit is wired to "The mountains are impassable." — confusing when
the player asks about a tree.

Detect the canonical climbables (tree, ladder, rope, vine, etc.) and
when the named object isn't actually present, print the topical
"There is no <X> here suitable for climbing." before any walk attempt.
"""

from moo.sdk import NoSuchObjectError, context

parser = context.parser
player = context.player

DIR_SET = {
    "up",
    "down",
    "u",
    "d",
    "north",
    "south",
    "east",
    "west",
    "n",
    "s",
    "e",
    "w",
}

target = parser.get_dobj_str() if parser.has_dobj_str() else "up"
target = target.strip().lower()

if target in DIR_SET:
    _.walk(target)
    return

# Non-direction dobj — try to resolve it in the current room/inventory.
try:
    dobj = parser.get_dobj() if parser.has_dobj_str() else None
except NoSuchObjectError:
    dobj = None

if dobj is None:
    print("There is no " + target + " here suitable for climbing.")
    return

# Object is in scope.  If it's marked climbable, walk("up"); otherwise
# print the canonical "you can't climb that" refusal.
if dobj.flag("climbable") or dobj.getp("vehicle", False):
    _.walk("up")
    return

print("I don't think much can be gained by climbing " + dobj.desc() + ".")
