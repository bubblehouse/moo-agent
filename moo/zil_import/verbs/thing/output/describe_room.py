#!moo verb describe_room --on "Thing" --dspec this
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Hand-written DESCRIBE-ROOM replacement.

Mirrors the auto-translated body but resolves the room-name banner
asymmetry: rooms with a per-room ``look`` verb (M-LOOK override) now
print the banner via the look verb (translator prepends
``print(this.desc())``), so describe_room must NOT also print the
banner before invoking that look — otherwise rooms with custom M-LOOK
double-render the heading ("Loud Room\\nLoud Room\\n...").  Rooms
WITHOUT a custom look still get the banner here so they don't lose it.
"""

from moo.sdk import NoSuchPropertyError, context

player = context.player
look_p = args[0] if len(args) > 0 else None

v_p = look_p or player.zstate_get("VERBOSE")
if not player.zstate_get("LIT"):
    print("It is pitch black.", end="")
    if not player.zstate_get("SPRAYED?"):
        print(" You are likely to be eaten by a grue.", end="")
    print()
    return False
if not player.here().flag("touchbit"):
    player.here().set_flag("touchbit", True)
    v_p = True
if player.here().flag("maze"):
    player.here().set_flag("touchbit", False)

here = player.here()
has_custom_look = here is not None and here.has_verb("look", recurse=False)

# Banner.  Canonical Zork prints ``<TELL D ,HERE CR>`` (the room name)
# at the top of DESCRIBE-ROOM whenever the room is lit.  ``here`` is
# always the player's current room, so the banner prints for every
# room that doesn't supply its own M-LOOK heading.  The old guard
# ``here.location == zstate_get("ROOMS")`` was unreliable: when the
# ROOMS pseudo resolved to a real object the equality failed for
# every (location=None) room, so goto-teleport destinations such as
# ``pray`` → Forest arrived bannerless (empty output / mangled PREFIX).
if not has_custom_look and here is not None:
    print(here.desc(), end="")
    av = player.location
    if av is not None and av.flag("vehicle"):
        print(", in the " + av.desc(), end="")
    print()

if (
    (look_p or not player.zstate_get("SUPER-BRIEF") or player.here() == player.zstate_get("ZORK3"))
    if player.zstate_get("ZORK-NUMBER") == 2
    else (look_p or not player.zstate_get("SUPER-BRIEF"))
):
    av = player.location
    if v_p and has_custom_look:
        # Custom M-LOOK handles its own describe_objects (translator appends
        # it to every M-LOOK).  Return False so callers (V-LOOK,
        # V-FIRST-LOOK) skip their post-describe_room describe_objects call
        # — otherwise items list twice (the duplicate-platinum-bar bug).
        here.invoke_verb("look")
        return False
    elif v_p:
        try:
            str_v = here.get_property("description")
        except NoSuchPropertyError:
            str_v = None
        if str_v:
            print(str_v)
        elif here is not None and here.has_verb("flashfunc", recurse=False):
            here.invoke_verb("flashfunc")
    if here != av and av is not None and av.flag("vehicle"):
        if av.has_verb("look", recurse=False):
            av.invoke_verb("look")
return True
