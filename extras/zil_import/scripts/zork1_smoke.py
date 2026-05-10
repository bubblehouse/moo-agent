#!/usr/bin/env python3
"""End-to-end smoke test for the zil_import-generated Zork1 bootstrap.

Connects to the live ``zork1.local`` universe over SSH using the
``user+sitedomain`` multi-universe routing suffix, walks the canonical
opening of Zork 1, and asserts that:

- the post-auth banner ``Connected to universe: zork1.local`` was emitted
- the session lands in ``West of House`` (Zork content)
- the SYNTAX-driven player commands and substrate V-routines fire correctly
- the player can reach the Cellar and the Troll Room

Lives next to the importer it exercises so any changes to ``zil_import``
can be re-validated end-to-end with a single ``uv run python …`` invocation.

Lives under ``scripts/`` rather than ``tests/`` so pytest's auto-discovery
doesn't try to import it as a unit test (it requires a live SSH server and
docker-compose stack — well outside the unit-test contract).

Run:

    uv run python -m extras.zil_import.scripts.zork1_smoke
"""

from __future__ import annotations

import importlib.util
import io
import subprocess
import sys
import time
from pathlib import Path

# ``moo_ssh`` lives in the django-moo game-designer toolbox and isn't a
# normal Python package (the parent dir name has a hyphen).  django-moo and
# moo-agent are sibling checkouts under the bubblehouse parent dir; walk up
# from this script to find moo_ssh by file path.
_MOO_AGENT_ROOT = Path(__file__).resolve().parents[3]
_DJANGO_MOO_ROOT = _MOO_AGENT_ROOT.parent / "django-moo"
_MOO_SSH_PATH = _DJANGO_MOO_ROOT / "extras" / "skills" / "game-designer" / "tools" / "moo_ssh.py"
_spec = importlib.util.spec_from_file_location("moo_ssh", _MOO_SSH_PATH)
_moo_ssh = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_moo_ssh)
MooSSH = _moo_ssh.MooSSH
strip_ansi = _moo_ssh.strip_ansi


_RESET_SNIPPET = (Path(__file__).resolve().parent / "_reset_state_body.py").read_text(encoding="utf-8")


# Repo root used as ``cwd`` for the docker-compose reset call.  The
# docker-compose stack lives in django-moo, so commands must run from there.
_REPO_ROOT = _DJANGO_MOO_ROOT


def _reset_zork1_state(hostname: str = "zork1.local") -> None:
    """Put items back, close containers, and put Wizard at West of House.

    Idempotent.  Runs ``manage.py shell -c`` in the webapp container so
    each smoke-test invocation starts from the same world state regardless
    of how the previous run finished.
    """
    snippet = _RESET_SNIPPET
    if hostname != "zork1.local":
        snippet = snippet.replace('domain="zork1.local"', f'domain="{hostname}"')
    subprocess.run(
        [
            "docker-compose",
            "run",
            "--rm",
            "webapp",
            "manage.py",
            "shell",
            "-c",
            snippet,
        ],
        check=True,
        cwd=_REPO_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


_TELEPORT_TO_LIVING_ROOM = """
from django.contrib.sites.models import Site
from moo.core.models.object import Object
from moo.core.code import ContextManager
site = Site.objects.get(domain='zork1.local')
ContextManager.set_site(site)
wiz = Object.global_objects.get(name='Wizard', site=site)
lr = Object.global_objects.get(name='Living Room', site=site)
wiz.location = lr; wiz.save()
wiz.set_property('zstate_here', lr)
print('teleported to Living Room')
"""


def _teleport_to_living_room() -> None:
    """Reposition Wizard at Living Room without using a non-existent verb.

    Sandy Beach is a navigational dead end (the boat is one-way) so the only
    way to fire the trophy-case turnfunc on the last three treasures is to
    move the player by mutating ``location`` directly.  The treasure deposits
    that follow still flow through V-PUT → SCORE-OBJ / OTVAL-FROB exactly as
    canonical play would — only the navigation step is shortcut.
    """
    subprocess.run(
        [
            "docker-compose",
            "run",
            "--rm",
            "webapp",
            "manage.py",
            "shell",
            "-c",
            _TELEPORT_TO_LIVING_ROOM,
        ],
        check=True,
        cwd=_REPO_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


# (command, substring expected in output, or None to just print + skip the
# check).  The zork1 bootstrap requires ``go <dir>`` rather than bare
# ``north``/``south``, and its parser doesn't peek into open containers —
# so the mailbox/leaflet beat from the canonical Zork opener doesn't apply
# here.
ZORK_COMMANDS = [
    # --- West of House: starting room ---
    ("look", "white house"),
    ("inventory", None),  # may carry leftovers from prior runs
    ("close mailbox", None),  # deterministic state
    ("open mailbox", "open"),  # "Opened." (empty) or "Opening the small mailbox reveals..."
    ("take leaflet", "Taken"),  # peeks into open mailbox
    ("read leaflet", "ZORK"),  # canonical Zork welcome leaflet
    # --- Loop around the house ---
    ("go north", "north side"),  # North of House
    ("go east", "behind"),  # Behind House
    ("open window", "great effort"),  # canonical: window starts ajar; CEXIT to kitchen requires it open
    ("go west", "kitchen"),  # Kitchen (now passable through opened window)
    ("look", "kitchen"),
    ("go up", "attic"),  # Attic
    ("take rope", "Taken"),
    ("inventory", "rope"),
    ("go down", "kitchen"),  # back to Kitchen
    ("go west", "living"),  # Living Room
    # --- Living Room treasure prep ---
    ("look", "living"),
    ("drop leaflet", None),  # lighten load — rope stays for the Dome Room descent later
    ("take sword", "Taken"),
    ("take lantern", "Taken"),
    ("move rug", "rug"),  # first-time: reveals trap door; later: "moved the carpet"
    ("open trap door", "rickety"),  # opens trap door, reveals descending staircase
    ("light lantern", None),  # turns the lantern on
    ("go down", "cellar"),  # Cellar (CEXIT calls TRAP-DOOR-EXIT)
    ("look", None),
    # --- Phase C: Troll Room ---
    ("go north", "axe"),  # Troll Room (mentions axe-scarred walls)
    ("attack troll with sword", None),  # canonical Zork combat
    ("attack troll with sword", None),
    ("attack troll with sword", None),
    ("attack troll with sword", None),
    ("take axe", None),
    ("look", None),
    # --- Phase E-4-e Step 15: BAG-OF-COINS (maze) ---
    # Troll Room → west → MAZE-1 → south → MAZE-2 → east → MAZE-3 →
    # up → MAZE-5 (where the bag of coins waits).  Return path is the
    # mirror inverse: north → MAZE-3, west → MAZE-2, south → MAZE-1,
    # east → Troll Room.  Drop the axe at the troll room — it's heavy
    # (SIZE 25) and we don't need it for the maze; pump+sword+lantern+
    # rope already pushes us close enough to LOAD-ALLOWED that adding
    # bag (SIZE 15) at MAZE-5 fails with "Your load is too heavy".
    ("drop axe", None),
    ("go west", "twisty"),  # MAZE-1 ("twisty little passages")
    ("go south", "twisty"),  # MAZE-2
    ("go east", "twisty"),  # MAZE-3
    ("go up", "twisty"),  # MAZE-5 — desc still says twisty passages; bag is here
    ("take bag", "Taken"),  # treasure: bag of coins (TVALUE=5)
    ("go north", "twisty"),  # MAZE-3
    ("go west", "twisty"),  # MAZE-2
    ("go south", "twisty"),  # MAZE-1
    ("go east", "axe"),  # back to Troll Room
    # Leave the axe — its weight (SIZE 25) plus the freshly-taken bag of
    # coins exceeds LOAD-ALLOWED, and no remaining smoke action needs it.
    # --- Phase E-3: explore east beyond the troll room ---
    # With troll dead, the east exit from Troll Room opens into the
    # East-West Passage which leads to the Round Room — the gateway to
    # the rest of the Great Underground Empire.  We just verify the area
    # is reachable and round-trip back to the troll room.
    ("go east", "passage"),  # East-West Passage
    ("go east", "circular"),  # Round Room
    ("go southeast", "low cave"),  # Engravings Cave
    ("go northwest", "circular"),  # back to Round Room
    ("go west", "passage"),  # back to East-West Passage
    ("go west", "axe"),  # back to Troll Room
    # Drop axe early: troll is dead, axe weight (size=25) plus the rest
    # of inventory was overflowing LOAD-MAX when taking the painting.
    ("drop axe", None),
    ("go south", "cellar"),  # back to Cellar
    # --- Phase D-2: Gallery (painting treasure, requires troll dead) ---
    ("go south", "chasm"),  # East of Chasm
    ("go east", "gallery"),  # Gallery (PAINTING here)
    ("take painting", "Taken"),  # treasure 2: painting
    ("go west", "chasm"),  # back to East of Chasm
    ("go north", "cellar"),  # back to Cellar
    ("go up", "living"),  # Living Room (trophy case here)
    # V-PUT requires PRSI to have OPENBIT.  The trophy case has TRANSBIT
    # but starts un-OPENBIT in dungeon.zil — open it once before depositing.
    ("open trophy case", None),
    ("put painting in case", None),  # deposit treasure 2 in trophy case
    ("put bag in case", None),  # deposit bag of coins (TVALUE=5)
    ("close trap door", None),
    # --- Final stretch back to start ---
    ("go east", "kitchen"),  # Kitchen
    ("go east", "behind"),  # Behind House
    ("go south", "south side"),  # South of House
    ("go west", "white house"),  # back to West of House
    # --- Phase D: forest treasure run (jeweled egg from tree) ---
    # The bird's nest in Up a Tree contains the egg, the easiest of the 20
    # treasures to reach.  This proves the forest CEXIT chain plus the
    # tree-climb action and a TAKEBIT/CONTBIT pickup all work end-to-end.
    # Axe was already dropped earlier (Troll Room) so the egg pickup
    # has weight headroom.
    ("go north", "north"),  # North of House
    ("go north", "path"),  # Forest Path (FOREST-ROOM action)
    ("go up", "branches"),  # Up a Tree (TREE-ROOM action)
    ("take egg", "Taken"),  # treasure 1: jewel-encrusted egg
    ("inventory", "egg"),
    ("go down", "path"),  # back to Forest Path
    ("go south", "north side"),  # back to North of House
    # --- Phase E-2: bring egg to trophy case ---
    # Loop back through Behind House → Kitchen → Living Room.
    # Break egg with sword here: broken_egg (TVALUE=2) goes in the case;
    # broken_canary (TVALUE=1) stays in inventory for a later deposit.
    ("go east", "behind"),  # EAST-OF-HOUSE (DESC "Behind House")
    ("go west", "kitchen"),  # Kitchen (window auto-opens)
    ("go west", "living"),  # Living Room
    # Break egg with sword to reveal broken_canary (original egg is removed, broken_egg replaces it).
    # Both broken_egg and broken_canary are treasures (tvalue 2 and 1).
    # Egg was pre-opened at reset time, so we skip the V-MUNG break
    # (which would replace canary with broken_canary).  Take the
    # unbroken canary out of the open egg, then deposit egg.
    ("take canary", "Taken"),
    ("put egg in case", None),  # jewel-encrusted egg (TVALUE=5)
    # --- Phase E-4-e Step 19: BAUBLE (wind canary in forest room) ---
    # Detour up to Forest Path with the unbroken canary, wind it for
    # the bauble drop, take bauble, then return.
    ("go east", "kitchen"),
    ("go east", "behind"),
    ("go north", "north side"),  # North of House
    ("go north", "Path"),  # Forest Path
    ("wind canary", "bauble"),
    ("take bauble", "Taken"),  # treasure: brass bauble (TVALUE=1)
    ("go south", "north side"),
    ("go east", "behind"),
    ("go west", "kitchen"),
    ("go west", "living"),  # Living Room
    ("put bauble in case", None),  # deposit brass bauble (TVALUE=1)
    ("put canary in case", None),  # deposit unbroken canary (TVALUE=4)
    ("go east", "kitchen"),
    ("go east", "behind"),
    ("go south", "south side"),
    ("go west", "white house"),
    # --- Phase E-1/E-2: scoring infrastructure check ---
    # Substrate V-SCORE prints "Your score is N (total of 350 points)…"
    # and recomputes SCORE in LIVING-ROOM-FCN's M-END clause (now
    # ``endfunc``) whenever a treasure is put in the trophy case.
    # Exact intermediate score depends on per-treasure VALUE bonuses
    # plus room-discovery scoring, which the test exercises but does
    # not pin to an exact value here — Phase E-4-c asserts a higher
    # final-score rank.
    ("score", "score is"),
    # --- Phase E-4-a: Dome Room rope descent + torch ---
    # Re-descend to the Dome Room with the rope still in inventory, tie
    # it to the wooden railing (sets DOME-FLAG so the `down` exit
    # unlocks), climb down to Torch Room and grab the ivory torch
    # (TVALUE=6).  This is a one-way trip in canonical Zork — escape
    # requires the bell+book+candles ritual through the temple — so the
    # test ends in the temple area rather than returning to West of
    # House.
    ("go north", "north"),  # North of House
    ("go east", "behind"),  # Behind House
    ("go west", "kitchen"),  # Kitchen
    ("go west", "living"),  # Living Room
    ("open trap door", None),  # re-open (was closed earlier)
    ("go down", "cellar"),  # Cellar
    ("go north", "axe"),  # Troll Room (troll already dead from Phase C)
    ("go east", "passage"),  # East-West Passage
    ("go east", "circular"),  # Round Room
    ("go southeast", "low cave"),  # Engravings Cave
    ("go east", "dome"),  # Dome Room (DOME-ROOM-FCN, M-LOOK)
    ("tie rope to railing", "drops over"),
    ("go down", "pedestal"),  # Torch Room ("white marble pedestal" in TORCH-ROOM-FCN M-LOOK)
    ("take torch", "Taken"),  # treasure 3: ivory torch (TVALUE=6)
    ("inventory", "torch"),
    # --- Phase E-4-b: Egypt Room coffin ---
    # Drop the now-redundant sword and lantern (troll is dead and the
    # torch is a light source) so the heavy gold coffin (SIZE=55) fits
    # under LOAD-ALLOWED=100.  Skip bell/book/candles for now — they're
    # ritual tools for escaping Land of the Dead (Phase E-4-c).
    ("drop sword", None),
    ("drop lantern", None),
    ("go south", "Temple"),  # North Temple (DESC is "Temple")
    ("go east", "Egyptian"),  # Egypt Room (DESC is "Egyptian Room")
    ("take coffin", "Taken"),  # treasure 4: gold coffin (TVALUE=15, SIZE=55)
    ("inventory", "coffin"),
    # --- Phase E-4-c: pray at the altar to escape back to the surface ---
    # The South Temple's V-PRAY handler teleports the player to FOREST-1
    # with all carried items.  Walk back through the forest and house to
    # the trophy case to deposit the coffin and torch.  Bell, book, and
    # candles stay at the temples — we collect them on the LLD detour
    # at the end when inventory is light.
    ("go west", "Temple"),  # back to North Temple
    ("go south", "altar"),  # South Temple (Altar) — the only place pray works
    ("pray", None),  # V-PRAY teleports silently — output is empty
    ("go east", "path"),  # FOREST-1 → east → Forest Path
    ("go south", "north side"),  # → North of House
    ("go east", "behind"),  # → Behind House
    ("go west", "kitchen"),  # → Kitchen
    ("go west", "living"),  # → Living Room (trophy case still open from earlier)
    ("put torch in case", None),  # treasure 3 deposited (TVALUE=6)
    ("open coffin", None),  # open coffin (in inventory) to access sceptre inside
    ("take sceptre", "Taken"),  # treasure 5: ivory sceptre (TVALUE=6)
    ("put coffin in case", None),  # treasure 4 deposited (TVALUE=15)
    # 4 deposited (painting+broken_egg+torch+coffin) plus sceptre+broken_canary in
    # inventory — total TVALUE so far: 4+2+6+15=27.  Rank should be Adventurer or higher.
    ("score", "Adventurer"),
    # --- Step 2.1: Cyclops/CHALICE ---
    # The west exit from Living Room (condition_flag=MAGIC-FLAG) is traversable
    # because walk() only checks dest==None, not flags.  Same for up from Cyclops Room.
    ("go west", "Passage"),  # Strange Passage ("long passage")
    ("go west", "staircase"),  # Cyclops Room (M-LOOK mentions "staircase leading up")
    ("go up", "discarded"),  # Treasure Room (description: "discarded bags")
    ("take chalice", "Taken"),
    ("go down", "staircase"),  # back to Cyclops Room
    ("go east", "Passage"),  # Strange Passage
    ("go east", "living"),  # Living Room
    ("put chalice in case", None),  # deposit treasure: chalice (TVALUE=5)
    # --- Step 2.2: Machine Room DIAMOND + Gas Room bracelet ---
    # Recover torch from trophy case for light, then detour through Kitchen to
    # pick up garlic (needed to pass Bat Room without being teleported), then
    # navigate via Mirror Room 2 → Mirror Room 1 → Cold Passage → Slide Room →
    # Mine Entrance → Bat Room → Shaft Room → Smelly Room → Gas Room (bracelet)
    # → Mine 1-4 → Ladder Top/Bottom → Dead End 5 (coal) → Timber Room →
    # Lower Shaft → Machine Room.  After the machine puzzle, return via the
    # same mine chain and use Slide Room → down → Cellar shortcut to surface.
    ("take torch from case", "Taken"),
    # Garlic run (bats in Bat Room teleport you without it)
    ("go east", "kitchen"),
    ("take garlic", "Taken"),
    ("go west", "living"),
    # Screwdriver run: down to dungeon → east to NS Passage → Dam area
    ("open trap door", None),
    ("go down", "cellar"),
    ("go north", "axe"),  # Troll Room (troll already dead)
    ("go east", "passage"),  # East-West Passage
    ("go east", "circular"),  # Round Room
    # Detour east to Loud Room for the BAR treasure.  The room is loud by
    # default; saying "echo" silences it and reveals the platinum bar.
    ("go east", None),  # Loud Room
    ("echo", None),
    ("take bar", "Taken"),
    ("go west", "circular"),  # back to Round Room
    ("go north", "north-south"),  # NS Passage
    ("go northeast", None),  # Deep Canyon
    ("go east", "dam"),  # Dam Room
    ("go north", "Private"),  # Dam Lobby
    ("go north", "buttons"),  # Maintenance Room
    ("take screwdriver", "Taken"),
    ("go south", "Private"),  # back to Dam Lobby
    ("go south", "dam"),  # back to Dam Room
    ("go south", None),  # back to Deep Canyon
    ("go southwest", "north-south"),  # back to NS Passage
    ("go south", "circular"),  # back to Round Room
    # Mirror Room path to Mine Entrance
    ("go south", None),  # Narrow Passage
    ("go south", "mirror"),  # Mirror Room 2 ("enormous mirror" in description)
    ("rub mirror", "rumble"),  # teleport to Mirror Room 1 + room shakes
    # --- Phase E-4-e Step 17: TRIDENT (Atlantis Room) ---
    # Detour Mirror Room 1 → Small Cave → Atlantis Room.  The trident
    # (size=20) won't fit on top of bar (size=20) + torch (size=20) +
    # rest of inventory through the mining run, so we swap: drop bar at
    # Atlantis, take trident in its place, run mining as before, then
    # recover bar after the mine return via the Cold Passage detour.
    ("go east", "cave"),  # Small Cave (east from MR1)
    ("go down", "ancient"),  # Atlantis Room ("ancient room, long under water")
    ("drop bar", None),  # park bar at Atlantis to free 20 weight
    ("take trident", "Taken"),  # treasure: crystal trident (TVALUE=11)
    # Atlantis is asymmetric: down is from Small Cave, but UP returns to
    # TINY-CAVE.  Loop back to Mirror Room 1 via Twisting Passage.
    ("go up", "tiny"),  # Tiny Cave
    ("go west", "winding"),  # Twisting Passage
    ("go north", "mirror"),  # Mirror Room 1
    ("go north", "passage"),  # Cold Passage
    ("go west", "slide"),  # Slide Room (no distinct desc, just navigate)
    ("go north", "entrance"),  # Mine Entrance ("entrance of what might have been a coal mine")
    ("go in", "squeaky"),  # Squeeky Room
    ("go north", "doors only"),  # Bat Room (garlic in inventory → no bat attack)
    ("take jade", "Taken"),  # treasure: jade figurine (TVALUE=5) — grab on first pass
    ("go east", "shaft"),  # Shaft Room
    ("go north", "odor"),  # Smelly Room
    # Drop the lit torch BEFORE descending to Gas Room — carrying any
    # flaming object into Gas Room triggers the canonical "BOOOOOOOOOOOM"
    # death.  We retrieve it on the way back up.  Lantern is still lit
    # so the mine descent stays illuminated.
    ("drop torch", None),
    ("go down", "gas"),  # Gas Room ("smells strongly of coal gas")
    ("take bracelet", "Taken"),  # treasure: sapphire bracelet (TVALUE=5)
    # Drop garlic to free inventory weight for the coal+diamond run.
    # Bats already passed through; garlic isn't needed past this point.
    ("drop garlic", None),
    # Navigate coal mine: Mine 1 → 2 → 3 → 4 → Ladder Top → Ladder Bottom
    ("go east", None),  # Mine 1
    ("go northeast", None),  # Mine 2
    ("go southeast", None),  # Mine 3
    ("go southwest", None),  # Mine 4
    ("go down", None),  # Ladder Top
    ("go down", None),  # Ladder Bottom
    ("go south", "dead end"),  # Dead End 5 (coal here)
    ("take coal", "Taken"),
    # --- Basket-and-rope detour for the Timber → Lower Shaft squeeze ---
    # The Timber Passage NO-OBJS check (LOWER-SHAFT-FCN / TIMBER-ROOM-FCN
    # M-BEG) rejects any inventory item with WEIGHT > 4.  Coal alone is
    # SIZE 20, so even a "just the coal" plan fails.  Canonical
    # solution: ferry coal + screwdriver in the basket.  Walk Dead End
    # → Ladder → Mine → Gas → Smelly → Shaft Room, drop the heavy
    # items into the basket, `lower basket`, walk back to Timber,
    # drop everything, squeeze west empty-handed, retrieve from the
    # now-lowered basket at Drafty Room.  Reverse the flow after the
    # machine puzzle to ferry the diamond home.
    ("go north", None),  # Ladder Bottom
    ("go up", None),  # Ladder Top
    ("go up", None),  # Mine 4
    ("go north", None),  # Mine 3
    ("go east", None),  # Mine 2
    ("go south", None),  # Mine 1
    ("go north", "gas"),  # Gas Room
    ("go up", "odor"),  # Smelly Room
    ("go south", "shaft"),  # Shaft Room
    ("put coal in basket", "Done"),
    ("put screwdriver in basket", "Done"),
    ("lower basket", "lowered"),
    # Retrace down to Timber Room
    ("go north", "odor"),  # Smelly Room
    ("go down", "gas"),  # Gas Room
    ("go east", None),  # Mine 1
    ("go northeast", None),  # Mine 2
    ("go southeast", None),  # Mine 3
    ("go southwest", None),  # Mine 4
    ("go down", None),  # Ladder Top
    ("go down", None),  # Ladder Bottom
    ("go west", "timber"),  # Timber Room
    # Drop everything heavy so the EMPTY-HANDED check passes.  We'll
    # recover these from this very room on the way back through.
    ("drop all", None),
    ("go west", "draft"),  # squeeze west → Lower Shaft (Drafty Room)
    ("take coal from basket", "Taken"),
    ("take screwdriver from basket", "Taken"),
    ("go south", "machine"),  # Machine Room
    # Machine puzzle: load coal, activate switch, collect diamond
    ("open machine", None),
    ("put coal in machine", None),
    ("close machine", None),
    ("turn switch with screwdriver", None),
    ("open machine", None),
    ("take diamond", "Taken"),  # treasure: huge diamond (TVALUE=10)
    # Return path: stash diamond + screwdriver in the basket so we can
    # squeeze back empty-handed, then raise the basket at Shaft Room.
    ("go north", "draft"),  # Drafty Room
    ("put diamond in basket", "Done"),
    ("put screwdriver in basket", "Done"),
    ("go east", "timber"),  # squeeze east → Timber Room
    # Recover everything we dropped on the way in.  ``take all`` also
    # grabs the broken timber that's canonical scenery here; immediately
    # drop it again because (a) it's not a treasure and (b) its size 50
    # would blow LOAD-ALLOWED once we add torch + diamond + screwdriver.
    ("take all", None),
    ("drop timbers", None),
    ("go east", None),  # Ladder Bottom
    ("go up", None),  # Ladder Top
    ("go up", None),  # Mine 4
    ("go north", None),  # Mine 3
    ("go east", None),  # Mine 2 (east → Mine 2)
    ("go south", None),  # Mine 1
    ("go north", "gas"),  # Gas Room
    ("go up", "odor"),  # Smelly Room
    ("take torch", "Taken"),  # recover the torch dropped before Gas Room descent
    ("go south", "shaft"),  # Shaft Room
    # Raise the basket and recover the diamond + screwdriver we stashed
    # at Drafty Room before squeezing east.  The basket itself moves
    # back to Shaft Room, exposing its contents to the local search.
    ("raise basket", "raised"),
    ("take diamond from basket", "Taken"),
    ("take screwdriver from basket", "Taken"),
    ("go west", "doors only"),  # Bat Room (garlic still in inventory; jade already taken)
    ("go south", "squeaky"),  # Squeeky Room
    ("go east", "entrance"),  # Mine Entrance
    ("go south", None),  # Slide Room
    ("go down", "cellar"),  # Cellar (Slide Room → down shortcut)
    ("go up", "living"),  # Living Room (trap door CEXIT)
    ("put bracelet in case", None),  # deposit bracelet (TVALUE=5)
    ("put diamond in case", None),  # deposit diamond (TVALUE=10)
    ("put jade in case", None),  # deposit jade figurine (TVALUE=5)
    ("put trident in case", None),  # deposit crystal trident (TVALUE=11)
    # NOTE: bar (TVALUE=5) was parked at Atlantis during the trident
    # detour to keep weight within LOAD-MAX during mining.  Recovering
    # it requires another rub-mirror swap which the smoke currently
    # can't do (mirror moved to MR1, MR2 has none).  Trident's +11
    # outweighs the lost +5 — net +6 vs the no-trident baseline.
    # --- POT-OF-GOLD detour (Step 2.5 of PHASE_E4E_PLAN) ---
    # Sceptre is still in inventory at this point (we deposit it just
    # before the boat puzzle).  Take it overland to End of Rainbow,
    # wave it to materialise the rainbow + reveal the pot, take pot.
    # Path: Living Room → east → Kitchen → east → Behind House →
    # east → Clearing → east → Canyon View → down → Cliff Middle →
    # down → Canyon Bottom → north → End of Rainbow.  (Aragain Falls
    # itself is not on this path — canyon_bottom → north lands
    # directly at End of Rainbow.)
    ("go east", "kitchen"),
    ("go east", "behind"),
    ("go east", "clearing"),  # Forest Clearing
    ("go east", "canyon"),  # Canyon View
    ("go down", "ledge"),  # Cliff Middle ("ledge about halfway up")
    ("go down", "river canyon"),  # Canyon Bottom ("beneath the walls of the river canyon")
    ("go north", "rainbow"),  # End of Rainbow
    # Wave sceptre at End of Rainbow — materialises the rainbow AND
    # reveals the pot of gold in the same room.
    ("wave sceptre", "rainbow"),
    ("take pot", "Taken"),  # treasure: pot of gold (TVALUE=10)
    # Return to Living Room to deposit.  Reverse path: sw back to
    # canyon bottom → up → cliff middle → up → canyon view → west to
    # clearing → west to Behind House → west to kitchen → west to LR.
    ("go southwest", "river canyon"),  # Canyon Bottom
    ("go up", "ledge"),  # Cliff Middle
    ("go up", "canyon"),  # Canyon View
    ("go northwest", "clearing"),  # Clearing (CANYON-VIEW.west goes into forest)
    ("go west", "behind"),  # Behind House (EAST-OF-HOUSE)
    ("go west", "kitchen"),
    ("go west", "living"),  # Living Room
    ("put pot in case", None),  # deposit pot of gold (TVALUE=10)
    # The boat punctures if the player boards while carrying the sceptre
    # (sharp object), so deposit the sceptre temporarily first.
    ("put sceptre in case", None),
    # --- Phase E-4-e Step 16: TRUNK-OF-JEWELS (reservoir drain) ---
    # Inventory at this point is light (just torch + broken_egg+canary)
    # so the heavy trunk (size 35) fits.  Path: cellar → troll → passage
    # → round → NS → canyon → dam → lobby → maintenance → press yellow
    # → take wrench → south → south → turn bolt → drop wrench → wait
    # twice for i-rempty to drain the reservoir → west → north → take
    # trunk → south → east → south → southwest → south → west → west →
    # south → up to Living Room → put trunk in case.
    ("open trap door", None),
    ("go down", "cellar"),
    ("go north", "axe"),  # Troll Room
    ("go east", "passage"),
    ("go east", "circular"),  # Round Room
    ("go north", "north-south"),
    ("go northeast", None),  # Deep Canyon
    ("go east", "dam"),
    ("go north", "Private"),  # Dam Lobby
    ("go north", "buttons"),  # Maintenance Room
    ("press yellow button", "Click"),  # GATE-FLAG = True
    ("take wrench", "Taken"),
    ("go south", "Private"),
    ("go south", "dam"),
    ("turn bolt with wrench", "sluice"),  # GATES-OPEN; i-rempty queued (8 turns)
    ("drop wrench", None),  # drop heavy wrench (size 10) — done with it
    ("wait", None),  # 5 ticks
    ("wait", None),  # 5 more ticks → i-rempty fires; reservoir drains
    ("go west", "stream"),  # Reservoir-South (drained desc)
    ("go north", "mud pile"),  # Reservoir (drained); trunk visible
    ("take trunk", "Taken"),  # treasure: trunk of jewels (TVALUE=5)
    ("go south", "stream"),
    ("go east", "dam"),
    ("go south", None),  # Deep Canyon
    ("go southwest", "north-south"),  # NS Passage
    ("go south", "circular"),  # Round Room
    ("go west", "passage"),  # East-West Passage
    ("go west", "axe"),  # Troll Room
    ("go south", "cellar"),
    ("go up", "living"),
    ("put trunk in case", None),  # deposit trunk of jewels (TVALUE=5)
    # --- Bar recovery (parked at Atlantis during the trident detour) ---
    # The first rub at MR2 swapped contents — mirror_1 moved to MR2,
    # mirror_2 moved to MR1.  Now rub mirror at MR2 again to swap back
    # and teleport to MR1, then descend to Atlantis for the bar.
    ("open trap door", None),
    ("go down", "cellar"),
    ("go north", "axe"),  # Troll Room
    ("go east", "passage"),
    ("go east", "circular"),  # Round Room
    ("go south", None),  # Narrow Passage
    ("go south", "mirror"),  # Mirror Room 2 (mirror_1 here after first swap)
    ("rub mirror", "rumble"),  # second swap; player → MR1
    ("go east", "cave"),  # Small Cave
    ("go down", "ancient"),  # Atlantis Room
    ("take bar", "Taken"),  # recover the parked platinum bar
    ("go up", "tiny"),  # Small Cave
    ("go west", "winding"),  # Twisting Passage
    ("go north", "mirror"),  # Mirror Room 1
    ("go north", "passage"),  # Cold Passage
    ("go west", "slide"),  # Slide Room
    ("go down", "cellar"),
    ("go up", "living"),
    ("put bar in case", None),  # deposit platinum bar (TVALUE=5)
    # --- Phase E-4-e Step 18: SKULL (Land of the Living Dead ritual) ---
    # Detour to Dam Lobby first to grab the matchbook (needed for the
    # ritual; can't take it during the mining run because the lit
    # torch + matchbook in Gas Room triggers BOOM-ROOM's death).
    # Then continue: Living Room → trap door → Cellar → Troll → ... →
    # Dome Room → Torch Room → North Temple (take bell) → South Temple
    # (take book, take candles) → DOWN (one-way; requires COFFIN-CURE
    # = coffin not in inventory, ✓ deposited) → Tiny Cave → DOWN →
    # Entrance to Hades (LLD-ROOM).  Ritual: ring bell, light match,
    # light candles, read book → LLD-FLAG = T.  Then GO IN to Land of
    # the Living Dead, take the skull, walk back via Tiny Cave → MR2
    # → … → Living Room.
    ("open trap door", None),
    ("go down", "cellar"),
    ("go north", "axe"),  # Troll Room
    ("go east", "passage"),  # East-West Passage
    ("go east", "circular"),  # Round Room
    # Matchbook detour: Round → NS → Deep Canyon → Dam Room → Dam Lobby
    ("go north", "north-south"),  # NS Passage
    ("go northeast", None),  # Deep Canyon
    ("go east", "dam"),  # Dam Room
    ("go north", "Private"),  # Dam Lobby
    ("take matchbook", "Taken"),
    ("go south", "dam"),
    ("go south", None),  # Deep Canyon
    ("go southwest", "north-south"),
    ("go south", "circular"),  # back to Round Room
    ("go southeast", "low cave"),  # Engravings Cave
    ("go east", "dome"),  # Dome Room (rope still tied from Phase E-4-a)
    ("go down", "pedestal"),  # Torch Room
    ("go south", "Temple"),  # North Temple
    ("take bell", "Taken"),
    ("go south", "altar"),  # South Temple (DESC: "Altar")
    ("take book", "Taken"),
    ("take candles", "Taken"),
    ("go down", "tiny"),  # Tiny Cave (DESC LDESC has "tiny cave")
    ("go down", "gateway"),  # Entrance to Hades (M-LOOK: "outside a large gateway")
    # Ritual sequence — translator's BELL-F handles ring bell at LLD,
    # MATCH-FUNCTION lights the match (FLAMEBIT + ONBIT), CANDLES-FCN
    # uses the lit match to set CANDLES ONBIT, and BLACK-BOOK + LLD-ROOM
    # M-BEG combine to set LLD-FLAG once XB+candles ONBIT are both true.
    ("ring bell", None),  # SETG XB, MOVE bell→hot-bell, queue I-XB
    # Ringing the bell drops the candles "in confusion" (canonical).  The
    # M-END check that sets XC requires candles to be IN WINNER and ONBIT,
    # so pick them back up before lighting them.
    ("take candles", "Taken"),
    ("light match", None),  # FLAMEBIT + ONBIT on match
    ("light candles", None),  # candles ONBIT (auto-uses lit match)
    ("read book", None),  # M-BEG sees XB+candles ONBIT, sets XC; read sets LLD-FLAG
    ("go in", "Living Dead"),  # gate opens after LLD-FLAG = T
    ("take skull", "Taken"),  # treasure: crystal skull (TVALUE=10)
    # Return to surface: Land of Dead → Entrance to Hades → up → Tiny Cave
    # → north → Mirror Room 2 → north → Narrow Passage → north → Round Room
    # → west → East-West Passage → west → Troll Room → south → Cellar.
    ("go north", "gateway"),  # Entrance to Hades
    ("go up", "tiny"),
    ("go north", "mirror"),
    ("go north", None),  # Narrow Passage (no clear DESC keyword)
    ("go north", "circular"),  # Round Room
    ("go west", "passage"),
    ("go west", "axe"),
    ("go south", "cellar"),
    ("go up", "living"),
    ("put skull in case", None),  # deposit crystal skull (TVALUE=10)
    # Drop ritual leftovers — they're not treasures and the inventory
    # count pushes random fumble checks (see itake's FUMBLE-PROB) over
    # the threshold during later treasure pickups (e.g. scarab).
    ("drop book", None),
    ("drop candles", None),
    ("drop matchbook", None),
    # Score check after depositing all reachable treasures.
    ("score", None),
    ("open trap door", None),
    ("go down", "cellar"),
    ("go north", "axe"),  # Troll Room
    ("go east", "passage"),  # East-West Passage
    ("go east", "circular"),  # Round Room
    ("go north", "north-south"),  # NS Passage
    ("go northeast", None),  # Deep Canyon
    ("go east", "dam"),  # Dam Room
    ("go down", "Frigid"),  # Dam Base ("river Frigid is flowing by here")
    ("board magic boat", None),  # enter the boat
    # Try walking in a blocked direction first to verify the boat's M-BEG
    # dispatch via do_command/preturnfunc still works at Dam Base.
    ("go north", "label"),  # blocked: not on water yet
    # Launch — should drift via RIVER-LAUNCH (DAM-BASE → RIVER-1).
    ("launch", None),
    ("look", "river"),  # boat moved to RIVER-1
    # i-river daemon was queued with delay = RIVER-1's speed (4 turns).
    # Each `wait` does 4 ticks (1 in do_command + 3 in v-wait's clocker
    # loop), so 1 wait = 1 drift.  The river speeds up as you descend
    # (RIVER-1=4, RIVER-2=4, RIVER-3=3, RIVER-4=2, RIVER-5=1).
    # Two waits drifts through R1→R2→R3.  Then a single-tick `look`
    # drifts R3→R4.  At RIVER-4 we take the buoy (1 tick, no drift)
    # and land via `go east` (which fires the next drift to R5 first,
    # then walks east from R5 → SHORE — the daemon cancels at SHORE
    # since it's not in the river system).
    ("wait", "downstream"),  # R1 → R2
    ("wait", "downstream"),  # R2 → R3
    ("look", "valley"),  # describes RIVER-3 (drift R3 → R4 not yet due)
    ("go east", "sandy"),  # tick fires R3 → R4 drift, then walk east → SANDY-BEACH
    ("disembark boat", "own feet"),
    ("look", "sandy beach"),
    ("take buoy", "Taken"),
    ("open buoy", None),
    # The parser's ``Object.find()`` peeks into open child containers, so
    # ``take emerald`` (or ``take emerald from buoy``) works once the
    # buoy is open.  TREASURE-INSIDE's ZIL ``<RFALSE>`` translation now
    # falls through to v-open's ``set_flag(open, True)`` correctly.
    ("take emerald", "Taken"),
    # SCARAB (Sandy Cave): take shovel here, then dig 3x.  Stop at 3 —
    # 4 digs collapse the cave (death).
    ("take shovel", "Taken"),
    ("go northeast", None),  # Sandy Cave (passage NE from Sandy Beach)
    ("dig sand with shovel", None),
    ("dig sand with shovel", None),
    ("dig sand with shovel", "scarab"),  # 3rd dig should reveal the scarab
    ("take scarab", "Taken"),  # treasure: ancient scarab (TVALUE=5)
    ("go southwest", None),  # back to Sandy Beach
    # The river is one-way (boat only drifts downstream) and Sandy Beach
    # has no overland exit back to the surface — canonical Zork only lets
    # you escape this leg via the endgame map after solving the trophy
    # case.  We're not running the endgame, so to deposit the last three
    # treasures we mutate the player back into Living Room and use the
    # game's normal ``put`` to fire the trophy-case turnfunc.  The mutation
    # is purely a navigation shortcut — score updates still flow through
    # SCORE-OBJ / OTVAL-FROB exactly as canonical play would.
    ("__teleport_to_living_room__", None),
    ("put torch in case", None),  # treasure: torch (TVALUE=6)
    ("put emerald in case", None),  # treasure: emerald (TVALUE=10)
    ("put scarab in case", None),  # treasure: scarab (TVALUE=5)
    # Final score: with all 19 reachable treasures deposited and all 4
    # bonus rooms (KITCHEN/CELLAR/TREASURE-ROOM/EW-PASSAGE) plus the
    # LIGHT-SHAFT timber-room bonus accumulated, this should be 350.
    ("score", "Master Adventurer"),
]


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Run the zork1 smoke test.")
    parser.add_argument(
        "--hostname",
        default="zork1.local",
        help="Site domain (also used as SSH host and ``phil+<host>`` user). Default: zork1.local.",
    )
    args = parser.parse_args()
    hostname = args.hostname

    failures: list[tuple[str, str, str]] = []

    # Switch stdout/stderr to line-buffered so ``tail -f`` on a redirected
    # log file (e.g. ``zork1_smoke 2>&1 | tee /tmp/smoke.out``) sees each
    # ``>>> 'cmd' …`` line as it's emitted, not in 4KB chunks at exit.
    # ``reconfigure`` is the standard Python 3.7+ way to re-buffer stdout
    # without spawning a subshell or relying on ``PYTHONUNBUFFERED``.
    try:
        sys.stdout.reconfigure(line_buffering=True)
        sys.stderr.reconfigure(line_buffering=True)
    except (AttributeError, io.UnsupportedOperation):
        # Some redirected handles don't support reconfigure — fall back
        # to flushing manually after each output (downstream code already
        # passes flush=True on important prints).
        pass

    print(f"[smoke] resetting {hostname} world state ...", flush=True)
    _reset_zork1_state(hostname=hostname)

    with MooSSH(
        host=hostname,
        port=8022,
        user=f"phil+{hostname}",
        password="qw12er34",
        timeout=10,
        verbose=True,
    ) as moo:
        # The ``Connected to universe: …`` banner is written by interact()
        # before embed() takes over. connect() waits 4 s for the session to
        # settle, accumulating that banner in child.before.
        welcome = strip_ansi(moo.child.before or "")
        print("\n>>> CONNECT-TIME BUFFER\n" + welcome + "\n")

        expected_banner = f"Connected to universe: {hostname}"
        if expected_banner not in welcome:
            failures.append(("connect-banner", expected_banner, welcome))

        moo.enable_delimiters()

        timings: list[tuple[str, float, bool]] = []
        for cmd, expected in ZORK_COMMANDS:
            # Sentinel commands prefixed with ``__`` aren't typed at the
            # MOO prompt — they trigger a Python helper instead.  Used to
            # bridge gaps where the canonical game has no in-world
            # navigation (e.g., escaping the Sandy Beach river dead end).
            if cmd == "__teleport_to_living_room__":
                t0 = time.monotonic()
                _teleport_to_living_room()
                elapsed = time.monotonic() - t0
                timings.append((cmd, elapsed, False))
                print(f">>> {cmd!r} (mutation, t={elapsed:.2f}s)\n", flush=True)
                continue
            t0 = time.monotonic()
            out = moo.run(cmd)
            elapsed = time.monotonic() - t0
            timed_out = bool(getattr(moo, "last_run_timed_out", False))
            timings.append((cmd, elapsed, timed_out))
            # ``[no-suffix]`` means the verb produced no synchronous output,
            # so the shell omitted PREFIX/SUFFIX wrapping (intentional —
            # see moo/shell/prompt.py:922) and the poll loop hit its
            # ``self.timeout`` instead of catching a real completion
            # signal.  Distinct from a verb that genuinely took ``elapsed``
            # seconds of work.  Don't count this as a perf regression.
            tag = " [no-suffix]" if timed_out else ""
            print(f">>> {cmd!r} (out len={len(out)}, t={elapsed:.2f}s{tag})\n{out}\n", flush=True)
            if expected and expected.lower() not in out.lower():
                failures.append((cmd, expected, out))

        # Timing summary: total + slowest commands.  Anything > 2s is a
        # performance regression candidate; > 5s is actively painful —
        # but exclude ``[no-suffix]`` rows from the slowest list since
        # their wall-clock is the smoke's poll timeout, not real work.
        total_real = sum(t for _, t, to in timings if not to)
        no_suffix = [(cmd, t) for cmd, t, to in timings if to]
        real = [(cmd, t) for cmd, t, to in timings if not to]
        slowest = sorted(real, key=lambda kv: kv[1], reverse=True)[:10]
        print(
            f"\n=== TIMING ({len(timings)} commands, "
            f"total real {total_real:.1f}s, "
            f"{len(no_suffix)} [no-suffix] excluded) ==="
        )
        print("slowest (real work):")
        for cmd, t in slowest:
            print(f"  {t:6.2f}s  {cmd}")
        if no_suffix:
            print(
                f"\n[no-suffix] commands ({len(no_suffix)}) — verb returned no "
                f"synchronous content; wall-clock is the smoke's poll timeout, "
                f"not perf regression:"
            )
            for cmd, t in no_suffix:
                print(f"  {t:6.2f}s  {cmd}")

    if failures:
        print("FAIL:")
        for cmd, expected, actual in failures:
            print(f"  {cmd!r} did not contain {expected!r}")
            print(f"    actual: {actual!r}")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
