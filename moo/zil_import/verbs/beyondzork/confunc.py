#!moo verb confunc --on "Actor"
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""Beyond Zork connect hook — enter persistent windowed display mode.

Beyond Zork drives a split-screen UI: a fixed top region holds the stats line
and the font-3 auto-map, painted by the renderer's ``window_*`` SDK calls; the
room text scrolls below.  The ZIL never issues a standalone "open the window"
opcode — its ``SPLIT`` calls resize an *already* windowed Z-machine screen — so
we open the persistent window here, once, when the player connects (the shell
fires ``player.confunc`` on connect, before any command runs).

This verb is Wizard-owned like every generated verb, so ``context.caller`` is the
Wizard and the wizard-gated :func:`open_window` SDK call is permitted even though
the connecting avatar (the Adventurer) is not a wizard.  Non-rich clients no-op;
GMCP clients get a ``Window.Open`` event.  ``height`` covers the tallest top-pane
content (the 11-row auto-map plus the stats/border rows).
"""

from moo.sdk import context, open_window

player = context.player

# Defensive parity with the default $player.confunc: ensure a location.
if not player.location:
    home = player.get_property("home") or _.player_start  # noqa: F821
    player.moveto(home)

# Enter windowed display mode; the renderer paints the top region on each look.
open_window(player, height=14, title="Beyond Zork")
