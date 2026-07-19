#!moo verb confunc --on "Actor"
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""Beyond Zork connect hook — choose the display mode for the client.

Beyond Zork drives a split-screen UI: a fixed top region holds the stats line
and the font-3 auto-map, painted by the renderer's ``window_*`` SDK calls; the
room text scrolls below.  The ZIL never issues a standalone "open the window"
opcode — its ``SPLIT`` calls resize an *already* windowed Z-machine screen — so
we open the persistent window here, once, when the player connects (the shell
fires ``player.confunc`` on connect, before any command runs).

Client capability decides which display the game itself drives, via Beyond
Zork's own ``DMODE`` flag (``T`` = enhanced/windowed, ``0`` = normal):

* **rich** clients (prompt_toolkit TUI) get the windowed top pane — open the
  window and leave ``DMODE`` at its seeded ``T``.  ``window_*`` calls paint the
  pane; ``V-LOOK`` routes the description into the DBOX and draws the auto-map.
* **raw** clients (line-oriented MUD clients, plain terminals — the shell
  no-ops every ``window_*`` event for them) get the *normal* display: set
  ``DMODE`` to ``0`` so ``V-LOOK`` sends the room description straight to the
  scroll via ``DESCRIBE-HERE`` and never calls ``DISPLAY-PLACE`` (no map, no
  DBOX).  This is exactly the degradation Beyond Zork shipped for terminals
  without a split screen.

This verb is Wizard-owned like every generated verb, so ``context.caller`` is the
Wizard and the wizard-gated :func:`open_window` SDK call is permitted even though
the connecting avatar (the Adventurer) is not a wizard.
"""

from moo.sdk import context, get_client_mode, open_window

player = context.player

# Defensive parity with the default $player.confunc: ensure a location.
if not player.location:
    home = player.get_property("home") or _.player_start  # noqa: F821
    player.moveto(home)

if get_client_mode() == "rich":
    # Enter windowed display mode; the renderer paints the top region on each
    # look.  height covers the tallest top-pane content (the 11-row auto-map
    # plus the stats/border rows).
    player.zstate_set("DMODE", True)
    open_window(player, height=14, title="Beyond Zork")
else:
    # Raw/line client: no top pane exists, so fall back to the normal
    # scroll-only display (description inline, no auto-map).
    player.zstate_set("DMODE", 0)
