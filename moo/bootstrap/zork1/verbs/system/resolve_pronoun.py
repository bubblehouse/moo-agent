#!moo verb resolve_pronoun --on "System Object"
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Replace pronouns (``it``, ``him``, ``her``) in ``parser.dobj_str`` with
the player's last-resolved dobj.

DjangoMOO's parser doesn't track pronoun bindings across commands.
This shim mirrors canonical ZIL's ``P-IT-OBJECT`` slot — the last
successful dobj is stored in ``zstate_pronoun_it`` (set by
``do_command.py`` after each turn), and on the next turn we substitute
it in when the player types ``it`` / ``him`` / ``her`` as the dobj.

The substitution only fires when:

- ``parser.dobj_str`` is exactly a pronoun word, and
- ``parser.dobj`` is unresolved (the parser couldn't find ``it`` as a
  real object), and
- the stored pronoun-Object still exists, and
- it's reachable from the player's current scope (inventory, current
  room, or the room's contents).

Otherwise the parser's own "There is no 'it' here." propagates.

:param args[0]: ``parser`` (the live ``Parser`` instance).
:param args[1]: ``player`` (the caller).
:param args[2]: ``loc`` (player's current location).
:returns: ``None``.  Mutates ``parser.dobj`` / ``parser.dobj_str`` in
    place when a pronoun is bound.
"""

from moo.sdk import context, lookup, NoSuchObjectError, NoSuchPropertyError

parser = args[0]
player = args[1]
loc = args[2]

PRONOUNS = {"it", "him", "her", "them"}

if parser is None:
    return
dobj_str = (parser.dobj_str or "").lower()
if dobj_str not in PRONOUNS:
    return
# Already resolved to a real object — leave it alone.
if parser.dobj is not None:
    return

try:
    pk = player.get_property("zstate_pronoun_it")
except NoSuchPropertyError:
    return
if pk is None:
    return
try:
    target = lookup(int(pk))
except NoSuchObjectError:
    return
if target is None:
    return

# Scope check: the pronoun's target must still be reachable.  Player
# inventory, the current location itself, or any sibling in the
# room's contents counts.  Children of the player's location's
# contents (open containers) also count.  Inline walk instead of a
# helper because RestrictedPython rejects ``_``-prefixed locals.
in_scope = False
if target == player or target == loc:
    in_scope = True
else:
    cur = target.location
    seen = 0
    while cur is not None and seen < 8:
        if cur == player or cur == loc:
            in_scope = True
            break
        cur = cur.location
        seen += 1

if not in_scope:
    return

parser.dobj = target
parser.dobj_str = (target.name or "").lower() or dobj_str
