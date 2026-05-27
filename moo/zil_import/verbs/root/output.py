#!moo verb desc global_in --on "Root"
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Output / scope helpers for Zork verbs.

desc:      no args; returns the object's short label — what ZIL's
           ``<PRINTD obj>`` prints (e.g. "Forest Path", "brass lantern").
           Translated routines call as ``obj.desc()``.

           For things, ``name`` and ``description`` are usually the
           same short string (e.g. both "leaflet"), so using ``name``
           matches existing behaviour.  For rooms, ``description`` is
           the long multi-line scenery text printed by DESCRIBE-ROOM;
           ``<PRINTD ,HERE>`` is meant to print only the short room
           label as a header, so returning ``name`` ("Forest Path") is
           what ZIL semantics require.  Returning the long description
           here caused the room description to print twice — once via
           PRINTD and again via the explicit description-property
           branch in DESCRIBE-ROOM.

           Display sanitization: ``_compute_display_names`` appends the
           atom suffix ``(ATOM)`` to disambiguate name collisions for
           ``--on "<name>"`` verb-load lookups. Players don't need that
           suffix; strip it from the player-visible label.

global_in: args[0] = location; True if ``this`` appears in the location's
           ``global_scenery`` list.  Called as ``obj.global_in(loc)``.
"""

import re

from moo.sdk import NoSuchPropertyError

if verb_name == "global_in":
    loc = args[0]
    try:
        scenery = loc.get_property("global_scenery")
    except NoSuchPropertyError:
        scenery = []
    if not scenery:
        return False
    # Scenery atoms come from the ZIL converter as uppercase hyphenated
    # tokens (``"GLOBAL-WATER"``); alias rows are snake_case lowercase
    # (``"global_water"``).  Normalize before the IN filter so the match
    # actually fires — otherwise ``global_water.global_in(here)`` always
    # returns False and ``drink water`` falls through to the "you have
    # to be holding the local globals" error.
    scenery_keys = {str(s).lower().replace("-", "_") for s in scenery}
    return this.aliases.filter(alias__in=scenery_keys).exists()
else:
    return re.sub(r" \([A-Z][A-Z0-9-]*\)$", "", this.name)
