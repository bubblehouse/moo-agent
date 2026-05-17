#!moo verb zil_init --on "Zork Thing" --dspec this
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Player-connect bootstrap shim for the canonical ZIL GO routine.

The full GO routine (``helpers/go.py``) does:
    - queue/schedule the always-on daemons,
    - set HERE / LIT / WINNER / PLAYER,
    - print the version banner,
    - run V-LOOK,
    - call MAIN-LOOP (the read loop — doesn't exist in our setup).

For DjangoMOO we only need the daemon scheduling part.  V-LOOK is
handled by do_command's normal dispatch on the player's first command
(usually ``look`` or a movement verb); the read loop is provided by
the shell.  And invoking ``go`` directly via ``invoke_verb`` clashes
with V-WALK-AROUND's ``go`` alias and prints "Use compass directions
for movement." instead of running the GO body — hence this shim.

Called once per session by ``do_command`` when ``zstate_started`` is
unset.
"""

# Recurring per-turn daemons: combat-round arbitration, sword-glow
# proximity check, thief patrol.
_.queue("i-fight", -1)
_.queue("i-sword", -1)
_.schedule_realtime("i_thief", -1)

# Fuel-decay daemons: lit candles and lantern burn out after N turns.
# The light verbs themselves re-queue these when an item is lit, but
# the at-connect call kicks them off in case the player picks up
# already-lit items at session start.
_.queue("i-candles", 40)
_.queue("i-lantern", 200)
