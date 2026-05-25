#!moo verb examine describe what whats x --on "Thing" --dspec this
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Hand-written V-EXAMINE replacement.

The auto-emitted body interpolates ``prso.desc()`` into the canonical
"There's nothing special about the X." line, which leaks the SSH
username when the player examines themselves (``examine me``).
Adds a ``prso == player`` short-circuit before the canonical
text / contbit / desc dispatch.

Canonical V-EXAMINE prints the object's description for the object
itself; for containers, it ADDITIONALLY shows the contents when open.
The earlier version delegated the contbit branch entirely to
V-LOOK-INSIDE, which for a closed or empty container prints "The X is
closed." / "The X is empty." and NEVER reaches the descriptive line —
turning ``examine chalice`` (closed) into a state-only report.
Re-order: print the descriptive line first, then add the contents view
only for open, non-empty containers.
"""

from moo.sdk import NoSuchObjectError, context

player = context.player
parser = context.parser

try:
    prso = parser.get_dobj() if parser.has_dobj_str() else None
except NoSuchObjectError:
    prso = None

if prso is None:
    if parser is not None and parser.has_dobj_str():
        print("There is no '" + parser.dobj_str + "' here.")
    else:
        print("What do you want to examine?")
    return

if prso == player:
    print("There's nothing special about yourself.")
    return

if prso.getp("text"):
    print(prso.getp("text"))
    return

if prso.flag("is_door"):
    return _.thing.look_inside()

# Print the canonical descriptive line first.  Use the typed dobj_str
# when present so multi-alias scenery objects (BEDROOM-FURNISHINGS bound
# to ``wall`` / ``wallpaper`` / ``carpet``) show the word the player
# actually typed rather than the canonical first synonym.
typed_word = parser.dobj_str.strip() if parser and parser.dobj_str else None
display = typed_word if typed_word else prso.desc()
print("There's nothing special about the " + display + ".")
# For open, non-empty containers, also show the contents.
if prso.flag("contbit") and not prso.flag("actorbit"):
    if prso.flag("open") and prso.contents.exists():
        _.thing.look_inside()
