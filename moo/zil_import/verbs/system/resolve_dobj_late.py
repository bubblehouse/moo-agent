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

from moo.sdk import NoSuchObjectError, NoSuchPropertyError, lookup

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

        # ZIL atom → object PK map (set by 030_objects.py).  Lets us
        # disambiguate scenery atoms whose snake-case alias collides
        # with another object's SYNONYM (HHG: CANOPY.SYNONYM includes
        # WINDOW, so ``lookup("window")`` returns CANOPY ahead of the
        # actual WINDOW Object).  When the map is missing (older
        # bootstrap) fall back to the alias lookup.
        try:
            atom_pk_map = _.get_property("zatom_pk_map") or {}
        except NoSuchPropertyError:
            atom_pk_map = {}

        found = None
        for area in areas:
            if found is not None:
                break

            scenery_atoms = area.getp("global_scenery", []) or []
            for atom in scenery_atoms:
                atom_str = str(atom)
                candidate = None
                pk = atom_pk_map.get(atom_str)
                if pk is not None:
                    try:
                        candidate = lookup(int(pk))
                    except NoSuchObjectError:
                        candidate = None
                if candidate is None:
                    try:
                        candidate = lookup(atom_str.lower().replace("-", "_"))
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

        # Bare-adjective fallback: ``push yellow`` is a single token
        # that doesn't match any object name or alias, but maintenance
        # room buttons carry ``yellow`` / ``red`` / ``brown`` / ``blue``
        # in their ``adjectives`` property.  When the dobj is still
        # unresolved and the token matches exactly one obvious object's
        # adjectives within the player's scope, bind to that object.
        # Ambiguous matches (multiple objects with the same adjective in
        # scope) fall through — the dispatcher will print "no X here"
        # rather than guessing.
        if found is None and parser.dobj_str and " " not in parser.dobj_str:
            adj_needle = parser.dobj_str.lower()
            adj_matches = []
            for area in areas:
                for obj in area.contents.all():
                    if not bool(obj.obvious):
                        continue
                    try:
                        adj_list = obj.get_property("adjectives") or []
                    except Exception:  # pylint: disable=broad-except
                        adj_list = []
                    if adj_needle in [str(a).lower() for a in adj_list]:
                        adj_matches.append(obj)
            if len(adj_matches) == 1:
                found = adj_matches[0]

        if found is not None:
            parser.dobj = found
            # Preserve the player's typed word as dobj_str.  Substrate verbs
            # that interpolate dobj_str into "There's nothing special about
            # the X." can then show what the player typed rather than the
            # canonical first-synonym name (BEDROOM-FURNISHINGS resolves
            # ``wall`` / ``wallpaper`` / ``carpet`` to the same Object but
            # we want each typed word reflected in the response).

# Self-pronoun substitution + global-scenery resolution for unresolved pobjs.
# Mirrors the dobj_str path so ``lie on bulldozer`` (where bulldozer lives in
# the room's global_scenery) and ``put coin on self`` both resolve before any
# substrate verb dispatches.
if parser is not None and parser.prepositions:
    try:
        atom_pk_map_p = _.get_property("zatom_pk_map") or {}
    except NoSuchPropertyError:
        atom_pk_map_p = {}
    areas_p = [player]
    if is_vehicle and loc is not None and loc is not physical_room:
        areas_p.append(loc)
    if physical_room is not None:
        areas_p.append(physical_room)
    for prep_recs in parser.prepositions.values():
        for rec in prep_recs:
            if rec[2] is not None or not rec[1]:
                continue
            obj_str = rec[1]
            if obj_str.lower() in SELF_PRONOUNS:
                rec[2] = player
                continue
            needle_p = obj_str.lower()
            found_p = None
            for area in areas_p:
                if found_p is not None:
                    break
                for atom in area.getp("global_scenery", []) or []:
                    atom_str = str(atom)
                    candidate = None
                    pk = atom_pk_map_p.get(atom_str)
                    if pk is not None:
                        try:
                            candidate = lookup(int(pk))
                        except NoSuchObjectError:
                            candidate = None
                    if candidate is None:
                        try:
                            candidate = lookup(atom_str.lower().replace("-", "_"))
                        except NoSuchObjectError:
                            continue
                    if not bool(candidate.obvious):
                        continue
                    cname = (candidate.name or "").lower()
                    if cname == needle_p:
                        found_p = candidate
                        break
                    for alias_row in candidate.aliases.all():
                        if alias_row.alias.lower() == needle_p:
                            found_p = candidate
                            break
                    if found_p is not None:
                        break
            if found_p is not None:
                rec[2] = found_p
