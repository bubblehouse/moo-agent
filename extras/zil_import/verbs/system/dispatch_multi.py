#!moo verb dispatch_multi --on "System Object"
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Multi-object dispatch for ``take all`` / ``drop all`` / ``take all but X``
and multi-noun forms (``take A and B``, ``drop X, Y``).

:param args[0]: Verb word (``"take"``, ``"drop"``, etc.).
:param args[1]: Parser (live ``context.parser``).
:param args[2]: Player Object.
:param args[3]: Physical-room Object (player's effective room).
:param args[4]: Location Object (``player.location`` — vehicle or room).
:param args[5]: ``is_vehicle`` bool.
:returns: ``True`` when the verb_word matched a multi-object form (caller
    should short-circuit); ``False`` to let normal dispatch proceed.
"""

from moo.sdk import UserError

TAKE_ALIASES = ("take", "get", "hold", "carry", "grab", "catch")
DROP_ALIASES = ("drop", "discard", "release")

verb_word = args[0]
parser = args[1]
player = args[2]
physical_room = args[3]
loc = args[4]
is_vehicle = args[5]

if verb_word not in TAKE_ALIASES + DROP_ALIASES or not parser.dobj_str:
    return False

dobj_lower = parser.dobj_str.lower().strip()

if dobj_lower == "all" or dobj_lower.startswith("all but "):
    # ``take all from <container>`` — gather from the named container
    # instead of the room.  The parser puts the container into the
    # ``from`` preposition slot; pull the resolved Object out and
    # enumerate its contents.
    container = None
    if verb_word in TAKE_ALIASES and parser.prepositions and "from" in parser.prepositions:
        from_entries = parser.prepositions["from"]
        if from_entries:
            entry = from_entries[0]
            if len(entry) >= 3 and entry[2] is not None:
                container = entry[2]
            elif len(entry) >= 2 and entry[1]:
                # Parser left the iobj unresolved (nested in an open
                # container).  Peek into open containers in the player's
                # inventory and current room — mirror the iobj-late
                # fallback added to put.py.
                needle = entry[1].lower()
                areas = [player]
                if physical_room is not None and physical_room != player:
                    areas.append(physical_room)
                if loc is not None and loc != physical_room and loc != player:
                    areas.append(loc)
                for area in areas:
                    for cand_container in area.contents.all():
                        match = _.peek_into(cand_container, needle, 4)
                        if match is not None:
                            container = match
                            break
                    if container is not None:
                        break

    if container is not None:
        # Refuse if the container isn't open (canonical Zork: "The X is closed.").
        if container.has_property("open") and not container.flag("open"):
            print("The " + (container.desc() or container.name or "container") + " is closed.")
            return True
        candidates = list(container.contents.all())
    elif verb_word in TAKE_ALIASES:
        scope = physical_room if physical_room is not None else loc
        candidates = _.gather_takeables(scope) if scope is not None else []
    else:
        candidates = list(player.contents.all())

    if dobj_lower.startswith("all but "):
        exclude = dobj_lower[len("all but ") :].strip()
        # Match against name OR any alias — players type "all but axe"
        # but the canonical object name is "bloody axe" with "axe" as
        # an alias.  Without alias-aware matching, ``take all but axe``
        # silently fails to exclude the axe.
        kept = []
        for c in candidates:
            if (c.name or "").lower() == exclude:
                continue
            matched_alias = False
            for a in c.aliases.all():
                if (a.alias or "").lower() == exclude:
                    matched_alias = True
                    break
            if not matched_alias:
                kept.append(c)
        candidates = kept

    if not candidates:
        if verb_word in TAKE_ALIASES:
            print("There is nothing here to take.")
        else:
            print("You aren't carrying anything.")
        return True

    for item in candidates:
        parser.dobj = item
        parser.dobj_str = item.name or ""
        print(f"{item.name or str(item)}:")
        try:
            item.invoke_verb(verb_word)
        except UserError as exc:
            print(f"  {exc}")
    return True

if "," in parser.dobj_str or " and " in parser.dobj_str:
    names = _.split_multi(parser.dobj_str)
    if len(names) > 1:
        for name in names:
            result = player.find(name)
            if not result and physical_room is not None:
                result = physical_room.find(name)
            if not result and is_vehicle and loc is not None and loc is not physical_room:
                result = loc.find(name)
            if not result:
                print(f"There is no '{name}' here.")
                continue
            item = result[0]
            parser.dobj = item
            parser.dobj_str = item.name or ""
            print(f"{item.name or str(item)}:")
            try:
                item.invoke_verb(verb_word)
            except UserError as exc:
                print(f"  {exc}")
        return True

return False
