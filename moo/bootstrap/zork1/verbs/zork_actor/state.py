#!moo verb zstate_get zstate_set --on "Zork Actor"
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""ZIL state primitives — per-player game state slots.

zstate_get: args[0] = key in UPPER-KEBAB-CASE (e.g. "CYCLOPS-FLAG")
zstate_set: args[0] = key, args[1] = value

Usage from caller code: ``context.player.zstate_get("CYCLOPS-FLAG")`` /
``context.player.zstate_set("CYCLOPS-FLAG", True)``.  Persists per-player
so multiple players have independent game state.  Falls back to the
System Object when the player has no per-player value for that key —
that's where bootstrap-level constants like the message tables (YUKS,
JUMPLOSS, …) live.
"""

import re

from moo.sdk import NoSuchPropertyError

raw_key = args[0]
sanitized = re.sub(r"[^a-z0-9_]", "_", raw_key.lower().replace("-", "_"))
if not sanitized:
    raise ValueError(f"zstate key cannot be empty (got {raw_key!r})")
key = "zstate_" + sanitized

if verb_name == "zstate_set":
    this.set_property(key, args[1])
    # Mirror ZIL's <SETG ...> which returns the new value — translated
    # code uses `not zstate_set(...)` to test the post-set state.
    return args[1]
else:
    try:
        return this.get_property(key)
    except NoSuchPropertyError:
        try:
            return _.get_property(key)
        except NoSuchPropertyError:
            return None
