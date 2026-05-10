#!moo verb pick --on "System Object"
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Pick a random element from a ZIL table.

ZIL tables typically have a leading length-marker (``0``) or ``"PURE"``
sentinel; those are skipped so callers don't see them as a return
value.

:param args[0]: Either a table list (e.g. ``zstate_get("YUKS")``), or
    a table name in UPPER-KEBAB-CASE (e.g. ``"HERO-MELEE"``), looked
    up on ``this`` as ``zstate_<lower_snake>``.
:returns: A randomly chosen entry, or ``None`` for empty / unknown tables.
"""

import random
import re

# ZIL table sentinels: ``0`` is a length marker, ``"PURE"`` is the
# read-only flag.  Neither is a valid ``pick`` result.
ZIL_TABLE_SENTINELS = (0, "PURE")

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
choices = [x for x in table if x not in ZIL_TABLE_SENTINELS]
if not choices:
    return None
return random.choice(choices)
