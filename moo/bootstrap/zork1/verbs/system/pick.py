#!moo verb pick --on "System Object"
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Pick a random element from a ZIL table.

ZIL message tables emit with a leading length-byte plus a ``0`` /
``"PURE"`` flag (e.g. ``[5, 0, "Hello.", "Good day.", …]``); the
header pair has to be skipped so V-HELLO / HACK-HACK don't surface
the count as a message string.  Combat tables (HERO-MELEE / MELEE-HERO
/ …) are shaped differently — outer lists of inner ``[weight, …]``
lists with no string entries at the outer level — so the filter has
to be shape-aware rather than "strings-only".

:param args[0]: Either a table list (e.g. ``zstate_get("YUKS")``), or
    a table name in UPPER-KEBAB-CASE (e.g. ``"HERO-MELEE"``), looked
    up on ``this`` as ``zstate_<lower_snake>``.
:returns: A randomly chosen entry, or ``None`` for empty / unknown
    tables.
"""

import random
import re

raw = args[0]
if isinstance(raw, list):
    table = raw
elif raw is None:
    return None
else:
    safe = re.sub(r"[^a-z0-9_]", "_", raw.lower().replace("-", "_"))
    if not safe:
        raise ValueError(f"zstate table name cannot be empty (got {raw!r})")
    key = "zstate_" + safe
    table = this.get_property(key)
# Message tables prefix entries with a ``[length, 0, …]`` header.  When
# we see that exact shape, strip the header.  Combat-style tables (lists
# of lists) don't match and pass through unchanged.
if len(table) >= 2 and isinstance(table[0], int) and table[1] == 0:
    choices = list(table[2:])
else:
    choices = list(table)
# ``"PURE"`` is a ZIL table read-only marker — never a valid pick.
choices = [x for x in choices if x != "PURE"]
if not choices:
    return None
return random.choice(choices)
