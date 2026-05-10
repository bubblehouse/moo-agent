#!moo verb split_multi gather_takeables --on "System Object"
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Multi-object dispatch helpers for ``take all`` / ``drop all`` / multi-noun
forms.  Called from ``do_command`` after the per-turn daemon tick and
preturnfunc forwarding.

``split_multi``: splits on commas and the word ``and`` while respecting
double quotes; returns a list of trimmed name strings (empty entries
dropped).

``gather_takeables``: returns a flat list of takeable Objects,
descending into open or transparent containers.  Skips the player and
``placement_prep`` of ``under`` / ``behind``.

:param args[0]: ``split_multi`` — dobj string;
    ``gather_takeables`` — root Object to scan.
:param args[1]: ``gather_takeables`` only — optional recursion depth
    (default ``4``).
:returns: ``split_multi`` — list of name strings;
    ``gather_takeables`` — list of takeable Objects.
"""

from moo.sdk import context

# Placement preps that hide objects until the player explicitly inspects
# (``look under``/``look behind``).  Skipped by ``gather_takeables``.
PLACEMENT_PREPS_HIDDEN = ("under", "behind")

if verb_name == "split_multi":
    s = args[0] if args else ""
    parts = []
    buf = []
    in_q = False
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == '"':
            in_q = not in_q
            buf.append(ch)
            i += 1
            continue
        if not in_q and ch == ",":
            parts.append("".join(buf).strip())
            buf = []
            i += 1
            continue
        if not in_q and s[i : i + 5] == " and ":
            parts.append("".join(buf).strip())
            buf = []
            i += 5
            continue
        buf.append(ch)
        i += 1
    parts.append("".join(buf).strip())
    return [p for p in parts if p]

if verb_name == "gather_takeables":
    # Canonical Zork: ``take all`` picks up takeable items in the room and
    # on top of non-takeable surfaces (e.g. the kitchen table) — but does
    # NOT extract contents from takeable containers (the sack stays packed
    # with lunch; the bottle stays full of water).  Recurse into a
    # container only when the container itself is non-takeable scenery.
    area = args[0] if args else None
    depth = args[1] if len(args) > 1 else 4
    player = context.player
    out = []
    if area is None or depth <= 0:
        return out
    for obj in area.contents.all():
        if obj is player:
            continue
        if obj.placement_prep in PLACEMENT_PREPS_HIDDEN:
            continue
        if obj.getp("takeable", False):
            out.append(obj)
            # Takeable containers stay packed (matches canonical "take all").
            continue
        if obj.getp("open", False) or obj.getp("transparent", False):
            out.extend(_.gather_takeables(obj, depth - 1))
    return out
