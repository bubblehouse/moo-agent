#!moo verb finish --on "Thing" --dspec this
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Hand-written HHG FINISH replacement (respawn instead of dead RESTART prompt).

Canonical ZIL FINISH shows the score, then offers RESTART/RESTORE/QUIT and
ends the session.  DjangoMOO is a persistent world with no session restart,
so the auto-translated finish() printed an unsupported "Restart not
supported. / Failed." prompt and then RETURNED — leaving a just-killed
player standing alive wherever they died.  Every non-<JIGS-UP> HHG death
funnels through FINISH (BETTER-LUCK demolition, GET-DRUNK, I-GROGGY,
BRICK-DEATH, RAMP-F), so all of them printed their death narrative and then
let the player keep playing.  Only <JIGS-UP> deaths respawned, because they
route to the System Object verbs/system/death.py which teleports home.

This replacement keeps the score readout, then respawns the player at
player_start (Bedroom) and bumps DEATHS — matching death.py so every HHG
death is consistent.  An explicit in-game ``quit`` still says Goodbye.

Skipped from the auto-emit via GameConfig.skip_routines={"FINISH"} (HHG
only); Zork keeps its generated FINISH (its JIGS-UP respawns directly, and
FINISH stays terminal there for the suicidal-maniac / quit cases).
"""

from moo.sdk import context

player = context.player
parser = context.parser
repeating = args[0] if len(args) > 0 else None

print()
if not repeating:
    # ZIL: <V-SCORE ...>
    _.thing.v_score()
    print()

word = parser.words[0] if (context.parser is not None and len(parser.words) >= 1) else ""
if word in (player.zstate_get("W?QUIT"), player.zstate_get("W?Q")):
    print("Goodbye.")
    return

# RESTART / RESTORE are unsupported in DjangoMOO's persistent world, and a
# just-killed player must not keep playing where they died.  Respawn at
# player_start (Bedroom) and increment DEATHS, mirroring verbs/system/death.py.
start = _.get_property("player_start")
if start is not None:
    player.location = start
    player.save()
player.zstate_set("DEATHS", (player.zstate_get("DEATHS") or 0) + 1)
return False
