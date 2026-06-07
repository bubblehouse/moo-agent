#!/usr/bin/env python3
"""End-to-end smoke test for the zil_import-generated Beyond Zork bootstrap.

Connects to the live ``beyondzork.local`` universe over SSH (raw / MooSSH
client → ``DMODE=0`` inline-description display) and walks the canonical
opening of *Beyond Zork: The Coconut of Quendor*, asserting that:

- the post-auth ``Connected to universe: beyondzork.local`` banner was emitted
- the session opens on the ``Hilltop`` (lit; carrying nothing) overlooking the
  seaside village
- the deterministic village + coast + Accardi spine works in both directions
- ``score`` fires (the RPG rank line)

The walk threads the whole verified opening into one continuous path: down the
hill into the village (Cove → Outside Pub → the Rusty Lantern → its Kitchen),
back out to the Cove and east onto the Wharf, then the coast road northeast/
northwest along the cliffs (Ledge → Tidal Flats) up into Accardi-by-the-Sea
(the Weapon Shop street → Outside Guild Hall → the ruined Lobby).  Extend the
command list room-by-room as the moors, the weapon-shop old-woman puzzle, and
the guild-hall plot are mapped and verified live (see the beyondzork-shakedown
skill).

Beyond Zork is the first XZIP (Z-machine v5) port and the first windowed title;
this smoke drives the *raw* (line-oriented) display only.  For the windowed
auto-map / DBOX rendering use the headless window-capture probe documented in
``.claude/skills/beyondzork-shakedown/references/known-quirks.md``.

This run also exercises the verbs fixed in the 2026-06-07 Mode-2 pass:
``inventory`` (VERB-SYNONYM parsing), ``wait`` (clocker shim), ``examine
<scenery>`` whose ACTION is a plain routine (USELESS dispatch), ``examine me``
(P-IT-OBJECT invariant), and the Weapon Shop room (SHOP-DOOR bare-object TELL).
Multi-statement room descriptions now render as continuous wrapped paragraphs
(the zout scroll-coalescing fix).

⚠️  KNOWN GAPS the spine still routes around (see the skill's BUGS.md):

* The first-exit M-EXIT gags (pub dagger-throw, guild-gate nymph) do NOT fire,
  so ``west`` out of the Rusty Lantern and ``north`` into the Lobby succeed
  cleanly.  When the M-EXIT/RFATAL traversal gap is fixed, those two steps WILL
  change (the dagger throw blocks the first west; the nymph blocks the first
  north) — update this spine then.
* The Weapon Shop emits a stray ``I don't know how to do that.`` line each turn
  (an old-woman M-ENTERING daemon); harmless, and room-name assertions are
  unaffected.
* The **forest** (west of the Babbling Brook) and the **moors** (south of
  Moor's Edge) are unreachable: their ``SCRAMBLE`` maze setup needs a
  byte-table exit-XROOM model the engine doesn't provide yet (BUGS.md). The
  spine walks to the Brook and back rather than into the forest.

Lives under ``scripts/`` (not ``tests/``) so pytest doesn't try to import it
— it requires a live SSH server + docker-compose stack.

Run::

    uv run python -m moo.zil_import.scripts.beyondzork_smoke 2>&1 | tee /tmp/smoke.out
"""

from __future__ import annotations

import argparse
import importlib.util
import io
import subprocess
import sys
import time
from pathlib import Path

# ``moo_ssh`` lives in the game-designer toolbox.  Prefer the in-repo
# (moo-agent) copy; fall back to the django-moo sibling checkout.
_MOO_AGENT_ROOT = Path(__file__).resolve().parents[3]
_MOO_SSH_PATH = _MOO_AGENT_ROOT / "extras" / "skills" / "game-designer" / "tools" / "moo_ssh.py"
if not _MOO_SSH_PATH.exists():
    _MOO_SSH_PATH = (
        _MOO_AGENT_ROOT.parent / "django-moo" / "extras" / "skills" / "game-designer" / "tools" / "moo_ssh.py"
    )
_spec = importlib.util.spec_from_file_location("moo_ssh", _MOO_SSH_PATH)
_moo_ssh = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_moo_ssh)
MooSSH = _moo_ssh.MooSSH
strip_ansi = _moo_ssh.strip_ansi

_CELERY = "django-moo-celery-1"
_SHELL = "django-moo-shell-1"


def _reset_beyondzork_state(hostname: str = "beyondzork.local") -> None:
    """Re-sync the world to its canonical opening (Celery stopped meanwhile).

    Runs ``moo_init --bootstrap beyondzork --sync`` which re-executes the
    generated ``099_reset_state.py`` (snapshot restore + canonical avatar
    placement at the Hilltop).  Celery is stopped for the duration so a live
    daemon tick can't deadlock the single-transaction sync, then restarted.
    """
    subprocess.run(["docker", "stop", _CELERY], capture_output=True, text=True, timeout=60, check=False)
    try:
        subprocess.run(
            [
                "docker",
                "exec",
                _SHELL,
                "sh",
                "-c",
                f"/usr/app/bin/python /usr/app/src/manage.py moo_init --bootstrap beyondzork --sync --hostname {hostname}",
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    finally:
        subprocess.run(["docker", "start", _CELERY], capture_output=True, text=True, timeout=60, check=False)


# (command, substring expected in output, or None to just print + skip the
# assertion).  Every assertion below was verified live on 2026-06-07.  Room
# names are matched as substrings so the raw-mode line-fragmentation (each
# zout fragment on its own line — see BUGS.md) doesn't break the check.
BEYONDZORK_COMMANDS = [
    ("look", "Hilltop"),  # opening room, lit, overlooking the Great Sea
    ("inventory", "zorkmid"),  # "You don't have anything except 1 zorkmid."
    ("east", "Cove"),  # "You amble down the hill."
    ("south", "Outside Pub"),  # Ye Rusty Lantern street
    ("in", "Rusty Lantern"),  # into the pub (bandits hogging the fireplace)
    ("west", "Kitchen"),  # cook + cellar door ("Keepeth Out.")
    ("examine cauldron", "nymph"),  # USELESS scenery → the "technical nymph" gag
    ("east", "Rusty Lantern"),  # back into the pub
    ("east", "Outside Pub"),  # out through PUB-DOOR
    ("north", "Cove"),
    ("east", "Wharf"),  # the salt warns you off the water
    ("west", "Cove"),
    # --- coast road north along the cliffs ---
    ("northeast", "Ledge"),  # crevice blasted into the cliff wall
    ("northwest", "Tidal Flats"),  # nameless brook meets the Great Sea
    ("northwest", "Babbling Brook"),  # inland coast road toward the forest edge
    ("southeast", "Tidal Flats"),  # back (the forest itself is maze-blocked — BUGS.md)
    ("northeast", "Accardi"),  # Accardi-by-the-Sea — the guild town
    ("west", "Weapon Shop"),  # SHOP-DOOR bare-object TELL no longer crashes
    ("east", "Accardi"),  # back out through WEAPON-DOOR
    ("east", "Outside Guild Hall"),  # headquarters of "The Circle"
    ("north", "Lobby"),  # ruined guild interior (magic-missile scorches)
    # --- core verbs (all fixed in the 2026-06-07 Mode-2 pass) ---
    ("wait", "Time passes"),  # clocker shim — no crash
    ("examine me", "Adventurer"),  # P-IT-OBJECT invariant: resolves to the avatar
    ("score", "rank"),  # "[Your rank is Level 0 Male Peasant, ...]"
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the beyondzork smoke test.")
    parser.add_argument(
        "--hostname",
        default="beyondzork.local",
        help="Site domain (used as the ``phil+<host>`` SSH user). Default: beyondzork.local.",
    )
    args = parser.parse_args()
    hostname = args.hostname

    failures: list[tuple[str, str, str]] = []

    try:
        sys.stdout.reconfigure(line_buffering=True)
        sys.stderr.reconfigure(line_buffering=True)
    except (AttributeError, io.UnsupportedOperation):
        pass

    print(f"[smoke] resetting {hostname} world state ...", flush=True)
    _reset_beyondzork_state(hostname=hostname)

    with MooSSH(
        host="localhost",
        port=8022,
        user=f"phil+{hostname}",
        password="qw12er34",  # nosec B106 — dev/test password
        timeout=10,
        verbose=True,
    ) as moo:
        welcome = strip_ansi(moo.child.before or "")
        print("\n>>> CONNECT-TIME BUFFER\n" + welcome + "\n")
        expected_banner = f"Connected to universe: {hostname}"
        if expected_banner not in welcome:
            failures.append(("connect-banner", expected_banner, welcome))

        moo.enable_delimiters()

        timings: list[tuple[str, float, bool]] = []
        for cmd, expected in BEYONDZORK_COMMANDS:
            t0 = time.monotonic()
            out = moo.run(cmd)
            elapsed = time.monotonic() - t0
            timed_out = bool(getattr(moo, "last_run_timed_out", False))
            timings.append((cmd, elapsed, timed_out))
            tag = " [no-suffix]" if timed_out else ""
            print(f">>> {cmd!r} (out len={len(out)}, t={elapsed:.2f}s{tag})\n{out}\n", flush=True)
            if expected and expected.lower() not in out.lower():
                failures.append((cmd, expected, out))

        total_real = sum(t for _, t, to in timings if not to)
        print(f"\n=== TIMING ({len(timings)} commands, total real {total_real:.1f}s) ===")

    if failures:
        print("FAIL:")
        for cmd, expected, actual in failures:
            print(f"  {cmd!r} did not contain {expected!r}")
            print(f"    actual: {actual!r}")
        return 1
    print(f"PASS ({len(BEYONDZORK_COMMANDS)} commands)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
