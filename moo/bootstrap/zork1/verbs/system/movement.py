#!moo verb remove goto walk perform next_sibling --on "System Object"
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Movement helpers for ZIL games.

Generic ZIL→DjangoMOO impedance — none of these reference Zork-specific
objects.  ``walk`` does the full exit-Object traversal that the substrate
``V-WALK`` would do via Z-machine table opcodes; everything else is a
direct property/location helper that's marginally too multi-line for the
translator to inline.

remove:  args[0] = object  (moves to None / limbo)
goto:    args[0] = destination room  (moves context.player or vehicle)
walk:    args[0] = direction string  (traverse the matching exit Object)
perform: args[0] = verb name string, args[1] = prso, args[2] = prsi
         Calls ACTION handler with explicit objects (ZIL PERFORM equivalent)
next_sibling: args[0] = object — returns the next sibling in
         ``args[0].location.contents`` (pk-ordered) or ``None``.  The ZIL
         translation of ``<NEXT? .CONT>`` calls this.

The ``here`` verb (vehicle-transparent room) lives on ``$player`` since it
reads from the player rather than taking explicit arguments.
"""

from moo.sdk import context


def place(target, destination):
    """
    Move ``target`` to ``destination`` and persist the change.

    :param target: Object to relocate.
    :param destination: New location (or ``None`` for limbo).
    """
    target.location = destination
    target.save()


def effective_room():
    """
    Effective current room: vehicle's location when inside one.

    :returns: The player's room, looking through any vehicle.
    """
    cur = _.current_vehicle()
    if cur is not None:
        return cur.location
    return context.player.location


if verb_name == "remove":
    place(args[0], None)

elif verb_name == "goto":
    veh = _.current_vehicle()
    if veh is not None:
        place(veh, args[0])
    else:
        place(context.player, args[0])

elif verb_name == "walk":
    direction = args[0]
    room = effective_room()
    if room is None:
        print("You can't go that way.")
        return
    exits = room.getp("exits", [])
    exit_obj = None
    for cand in exits or []:
        if cand.aliases.filter(alias=direction).exists():
            exit_obj = cand
            break
    if exit_obj is None:
        print("You can't go that way.")
        return
    # Delegate to the exit's `move` verb (per-exit overrides + zork_exit/move.py default).
    exit_obj.invoke_verb("move", context.player)

elif verb_name == "perform":
    verb_str = args[0]
    prso = args[1] if len(args) > 1 else None
    prsi = args[2] if len(args) > 2 else None
    # ZIL re-dispatch with explicit objects (e.g. V-DISEMBARK recursing with vehicle as PRSO).
    if prso is not None:
        context.parser.dobj = prso
        context.parser.dobj_str = prso.name
    if prsi is not None:
        # Re-seeding parser.prepositions is fragile; expose iobj directly as a fallback.
        try:
            context.parser.iobj = prsi
        except AttributeError:
            pass
    if prso is not None and prso.has_verb(verb_str):
        prso.invoke_verb(verb_str, prso, prsi)

elif verb_name == "next_sibling":
    obj = args[0] if args else None
    if obj is None or obj.location is None:
        return None
    siblings = list(obj.location.contents.order_by("pk"))
    seen = False
    for sib in siblings:
        if seen:
            return sib
        if sib.pk == obj.pk:
            seen = True
    return None
