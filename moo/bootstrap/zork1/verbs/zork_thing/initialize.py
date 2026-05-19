#!moo verb initialize --on "Zork Thing"
# pylint: disable=undefined-variable
"""Grant ``everyone`` move + write permissions on every new Zork Thing.

- ``move`` is required for take/drop (location change per object.py:1011).
- ``write`` is required by ``set_property`` (object.py:738) for any flag
  mutation — invisible, touchbit, open, etc.  Most things mutate state
  during gameplay (TOUCH-ROOM clears INVISIBLE, take sets TOUCHBIT, …),
  so without ``write`` the canonical room-entry side effects fail silently
  and items stay un-takeable for non-owner players.

The ``owners`` group already grants ``anything`` to self-owned objects;
these grants are the additional rules needed for non-owner players to
manipulate items.

Containers / Actor NPCs override this verb and use ``passthrough()`` to
inherit both grants from here.
"""

this.allow("everyone", "move")
this.allow("everyone", "write")
