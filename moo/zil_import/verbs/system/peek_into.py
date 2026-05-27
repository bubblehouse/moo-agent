#!moo verb peek_into --on "System Object"
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Recursive search through open or transparent containers for an Object
matching a name or alias.  Used by ``do_command``'s late dobj resolution
so commands like ``take emerald`` work when the emerald is inside an
opened buoy in the player's inventory.  Skips contents whose
``placement_prep`` is ``under`` or ``behind`` — those need an explicit
``look under``.

:param args[0]: Container Object to search.
:param args[1]: Needle string (lowercased name/alias to match).
:param args[2]: Optional recursion depth (default ``4``).
:returns: The first matching Object, or ``None``.
"""

# Placement preps that hide objects until the player explicitly inspects.
PLACEMENT_PREPS_HIDDEN = ("under", "behind")

container = args[0] if args else None
needle = args[1] if len(args) > 1 else ""
depth = args[2] if len(args) > 2 else 4

if container is None or depth <= 0 or not needle:
    return None

if not (container.getp("open", False) or container.getp("transparent", False)):
    return None

for inner in container.contents.all():
    if inner.placement_prep in PLACEMENT_PREPS_HIDDEN:
        continue
    iname = (inner.name or "").lower()
    if iname == needle:
        return inner
    for alias_row in inner.aliases.all():
        if alias_row.alias.lower() == needle:
            return inner
    deeper = _.peek_into(inner, needle, depth - 1)
    if deeper is not None:
        return deeper
return None
