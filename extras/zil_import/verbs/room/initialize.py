#!moo verb initialize --on "Room"
# pylint: disable=undefined-variable
"""Grant ``everyone`` write on every new Room instance.

Rooms mutate per-room flags via ``set_property`` (write); they don't
relocate so no ``move`` grant is needed.
"""

this.allow("everyone", "write")
