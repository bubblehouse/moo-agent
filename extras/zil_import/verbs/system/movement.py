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
    dest = args[0] if args else None
    if veh is not None:
        place(veh, dest)
    else:
        place(context.player, dest)
    # Canonical ZIL <GOTO> is the room-change routine: it relocates the
    # player AND describes the destination.  The bare relocate above
    # left every <GOTO> caller (V-PRAY, mirror-rub teleports, i-river
    # drift, jigs_up respawn) on a silent, undescribed room — the
    # player saw nothing until the next `look`.  Update HERE / LIT and
    # run V-FIRST-LOOK so the destination renders, the same way the
    # exit-traversal path describes a room you walk into.
    if dest is not None:
        context.player.zstate_set("HERE", dest)
        context.player.zstate_set("LIT", _.thing.is_lit(dest))
        _.thing.first_look()

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
    # Delegate to the exit's `move` verb (per-exit overrides + exit/move.py default).
    exit_obj.invoke_verb("move", context.player)

elif verb_name == "perform":
    verb_str = args[0]
    prso = args[1] if len(args) > 1 else None
    prsi = args[2] if len(args) > 2 else None
    # ZIL ``<PERFORM ,V?X ,O ,I>`` re-dispatch: mutate parser PRSO/PRSI/verb-word,
    # invoke the target verb on PRSO, restore in ``finally``.  Restore matters
    # for action handlers that call PERFORM then return — the caller still
    # holds the original parser state (e.g. HHG ROBOT-PANEL-F PUT-ON branch:
    # ``_.perform('block_with', this, prso); return True`` — without restore,
    # the caller's next read of ``the_player_verb`` sees the inner verb name).
    #
    # Word swap is critical for ``invoked_verb_name(verb_name)`` consumers
    # (translated bodies read ``the_player_verb = invoked_verb_name(verb_name)``
    # then branch on it).  Without it, re-entering an OBJECT-FUNCTION takes
    # the same branch as the caller and recurses indefinitely.
    parser = context.parser
    prior_dobj = parser.dobj if parser is not None else None
    prior_dobj_str = parser.dobj_str if parser is not None else None
    prior_words = list(parser.words) if parser is not None and parser.words else None
    prior_prepositions = None
    if parser is not None and parser.prepositions is not None:
        prior_prepositions = {p: [list(r) for r in recs] for p, recs in parser.prepositions.items()}
    try:
        if parser is not None:
            if prso is not None:
                parser.dobj = prso
                parser.dobj_str = prso.name
            if prior_words is not None:
                new_words = list(prior_words)
                new_words[0] = str(verb_str)
                parser.words = new_words
            if prsi is not None:
                # Single-prep PRSI placement under "with" — most consumers read
                # via ``parser.get_iobj()`` which walks every prep and returns
                # the first resolved Object.  Keeping it under a single prep
                # avoids confusing has_pobj(prep) callers that check a specific
                # preposition (those will see the original-prep cleared, which
                # is correct for the re-dispatched verb).
                parser.prepositions = {"with": [["", prsi.name, prsi]]}
            elif parser.prepositions is not None:
                parser.prepositions = {p: [] for p in parser.prepositions}
        if prso is not None and prso.has_verb(verb_str):
            # Don't pass prso/prsi as positional args.  God-verbs (OBJECT-FUNCTION
            # routines like troll/break.py) read ``mode = args[0]``; passing the
            # object as args[0] makes mode truthy, the body's ``if not mode``
            # guard skips the player-command handlers, and the verb falls
            # through to ``passthrough()`` — which routes back through the
            # actor dispatcher and re-enters V-SGIVE, recursing without bound.
            prso.invoke_verb(verb_str)
    finally:
        if parser is not None:
            parser.dobj = prior_dobj
            parser.dobj_str = prior_dobj_str
            if prior_words is not None:
                parser.words = prior_words
            if prior_prepositions is not None:
                parser.prepositions = prior_prepositions

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
