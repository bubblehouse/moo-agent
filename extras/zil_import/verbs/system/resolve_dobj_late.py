#!moo verb resolve_dobj_late --on "System Object"
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Late dobj/pobj resolution for scenery atoms, open-container peek, and
self-pronouns (``self`` / ``myself`` / ``yourself``).

Mutates the live parser in-place: ``parser.dobj`` / ``parser.dobj_str``
get filled in when a match is found among the player's inventory open
containers, the vehicle (if any), or the physical room's
``global_scenery``.  Same self-pronoun substitution is applied to any
unresolved iobj/pobj entries in ``parser.prepositions``.

:param args[0]: Parser (live ``context.parser``).
:param args[1]: Player Object.
:param args[2]: Location Object (``player.location``).
:param args[3]: Physical-room Object (effective room).
:param args[4]: ``is_vehicle`` bool.
"""

from moo.sdk import NoSuchObjectError, lookup

SELF_PRONOUNS = ("self", "myself", "yourself")

parser = args[0]
player = args[1]
loc = args[2]
physical_room = args[3]
is_vehicle = args[4]

if parser is not None and parser.dobj is None and parser.dobj_str:
    needle = parser.dobj_str.lower()

    # Self-pronoun shortcut: ``examine self`` etc. binds dobj = caller.
    if needle in SELF_PRONOUNS:
        parser.dobj = player
        if player.name:
            parser.dobj_str = player.name
    else:
        # Inventory first (open containers carried by the player), then
        # vehicle (if any), then physical room.
        areas = [player]
        if is_vehicle and loc is not None and loc is not physical_room:
            areas.append(loc)
        if physical_room is not None:
            areas.append(physical_room)

        found = None
        for area in areas:
            if found is not None:
                break

            scenery_atoms = area.getp("global_scenery", []) or []
            for atom in scenery_atoms:
                try:
                    candidate = lookup(str(atom).lower().replace("-", "_"))
                except NoSuchObjectError:
                    continue
                if not bool(candidate.obvious):
                    continue
                cname = (candidate.name or "").lower()
                if cname == needle:
                    found = candidate
                    break
                for alias_row in candidate.aliases.all():
                    if alias_row.alias.lower() == needle:
                        found = candidate
                        break
                if found is not None:
                    break
            if found is not None:
                break

            for container in area.contents.all():
                found = _.peek_into(container, needle, 4)
                if found is not None:
                    break

        if found is not None:
            parser.dobj = found
            if found.name:
                parser.dobj_str = found.name

# Self-pronoun substitution for unresolved pobjs (``put coin on self``).
if parser is not None and parser.prepositions:
    for prep_recs in parser.prepositions.values():
        for rec in prep_recs:
            if rec[2] is None and rec[1] and rec[1].lower() in SELF_PRONOUNS:
                rec[2] = player
