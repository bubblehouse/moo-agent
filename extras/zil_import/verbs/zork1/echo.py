#!moo verb echo --on "Actor"
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""Stub for V-ECHO. Loud Room's W?ECHO branch silences the room and sets
LOUD-FLAG; per-room handlers cover that via M-ENTER. This fallback prints
a canonical reverberation for every other room."""

from moo.sdk import context, lookup, NoSuchObjectError

player = context.player
try:
    loud_room = lookup("loud_room")
except NoSuchObjectError:
    loud_room = None
if loud_room is not None and player.location == loud_room and not player.zstate_get("LOUD-FLAG"):
    player.zstate_set("LOUD-FLAG", True)
    try:
        platinum_bar = lookup("bar")
        platinum_bar.obvious = True
        platinum_bar.save()
    except NoSuchObjectError:
        pass
    print("The acoustics of the room change subtly.")
else:
    print("echo echo ...")
