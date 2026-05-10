#!moo verb do_command --on "System Object"
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
LambdaMOO ``$do_command`` pre-dispatch hook for ZIL games.

Called by ``moo/core/parse.py:interpret()`` before normal verb dispatch.

Responsibilities (in dispatch order):

1.  ``again`` / ``g`` repeat-last-command via ``zstate_last_command``.
2.  Per-turn daemon tick (``i-river`` drift, ``i-lantern`` dim, …).
3.  Forwarding to ``preturnfunc`` (ZIL M-BEG) on the player's location
    and on any underlying physical room when the location is a vehicle.
4.  Late dobj resolution — see ``resolve_dobj_late.py``.
5.  Multi-object dispatch (``take all`` / ``drop A and B``) — see
    ``dispatch_multi.py``.

Helpers extracted to sibling System Object verbs:

* ``rehydrate_preps`` / ``dehydrate_preps`` — see ``again_state.py``.
* ``split_multi`` / ``gather_takeables`` — see ``take_helpers.py``.
* ``peek_into`` — see ``peek_into.py``.
* ``resolve_dobj_late`` — see ``resolve_dobj_late.py``.
* ``dispatch_multi`` — see ``dispatch_multi.py``.

:param args[0]: The verb word the player typed.
:returns: ``True`` to short-circuit normal dispatch; ``False`` /
    falsy to let the parser proceed to verb resolution.
"""

from moo.sdk import context, NoSuchObjectError, lookup


player = context.player
parser = context.parser
verb_word = (args[0] if args else "").lower()
is_again = verb_word in ("again", "g")

# ``again`` / ``g`` — restore last command into the live parser.
if is_again:
    snap = player.getp("zstate_last_command", None)
    if not snap:
        print("You haven't done anything to repeat yet.")
        return True
    parser.command = snap.get("command", "")
    parser.words = list(snap.get("words") or [])
    parser.dobj_str = snap.get("dobj_str")
    parser.dobj_spec_str = snap.get("dobj_spec_str")
    dpk = snap.get("dobj_pk")
    if dpk is not None:
        try:
            parser.dobj = lookup(int(dpk))
        except NoSuchObjectError:
            parser.dobj = None
    else:
        parser.dobj = None
    parser.prepositions = _.rehydrate_preps(snap.get("preps") or {})
    verb_word = parser.words[0].lower() if parser.words else ""

loc = player.location
if loc is None:
    return False

# Tick the queue FIRST so per-turn daemons fire before preturnfunc and main
# dispatch — lets a vehicle's drift land before the player's command runs.
_.tick()

# i-river may have moved the boat (and player with it) during tick.
loc = player.location
if loc is None:
    return False
is_vehicle = bool(loc.getp("vehicle", False))

player_verb_arg = parser.words[0] if parser.words else None

if is_vehicle:
    if loc.has_verb("preturnfunc"):
        if loc.invoke_verb("preturnfunc", "M-BEG", player_verb_arg):
            return True
    physical_room = loc.location
else:
    physical_room = loc

if physical_room is not None and physical_room.has_verb("preturnfunc"):
    if physical_room.invoke_verb("preturnfunc", "M-BEG", player_verb_arg):
        return True

# The parser reads ``self.dobj`` inside ``get_search_order`` *after*
# ``__init__`` returns, so mutating it here is well-defined: the dobj we
# set will appear in the verb-dispatch search order naturally.
_.resolve_dobj_late(parser, player, loc, physical_room, is_vehicle)

# Snapshot BEFORE the multi-object short-circuits below, so ``again`` after
# ``take all`` re-runs ``take all``.  Skip on empty verb_word and on the
# servicing-``again`` path (otherwise the snapshot is self-referential).
if not is_again and verb_word:
    try:
        snap_dobj_pk = parser.dobj.pk if parser.dobj is not None else None
        snap = {
            "command": parser.command,
            "words": list(parser.words),
            "dobj_str": parser.dobj_str,
            "dobj_spec_str": parser.dobj_spec_str,
            "dobj_pk": snap_dobj_pk,
            "preps": _.dehydrate_preps(parser.prepositions or {}),
        }
        player.set_property("zstate_last_command", snap)
    except (AttributeError, TypeError):
        pass

if _.dispatch_multi(verb_word, parser, player, physical_room, loc, is_vehicle):
    return True

return False
