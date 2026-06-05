#!/usr/bin/env python3
"""End-to-end smoke test for the zil_import-generated Zork II bootstrap.

Connects to the live ``zork2.local`` universe over SSH, walks the canonical
opening of Zork II (Inside the Barrow → Narrow Tunnel → Foot Bridge → Great
Cavern → Shallow Ford → Dark Tunnel → Path Near Stream → Formal Garden) and
asserts that:

- the post-auth ``Connected to universe: zork2.local`` banner was emitted
- the session opens in ``Inside the Barrow`` (lit; lamp + sword on the floor)
- core verbs fire correctly: ``take`` / ``drop`` / ``turn on`` / ``examine``
  / ``inventory``
- the deterministic movement spine works and a blocked exit fails cleanly

It then takes the Formal Garden side-trips (North End of Garden, where the
unicorn bounds away; Topiary) and traverses the Carousel Room — the spinning
hub SW of Path Near Stream.  The carousel randomizes its exits while
``CAROUSEL-FLIP-FLAG`` is unset; the reset body seeds that flag True (the
smoke-safe shortcut for the robot/triangular-button puzzle), so the smoke can
walk N → Marble Hall deterministically.  From Marble Hall it continues north
through the ravine (Deep Ford → Ledge in Ravine → End of Ledge) to the Dragon
Room, where ``examine dragon`` triggers the dragon's gaze (DRAGON-FCN).
Extend the command list room-by-room as later puzzles are mapped and verified
live (see the zork2-shakedown skill).

Lives under ``scripts/`` (not ``tests/``) so pytest doesn't try to import it
— it requires a live SSH server + docker-compose stack.

Run::

    uv run python -m moo.zil_import.scripts.zork2_smoke 2>&1 | tee /tmp/smoke.out
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


def _reset_zork2_state(hostname: str = "zork2.local") -> None:
    """Re-sync the world to its canonical opening (Celery stopped meanwhile).

    Runs ``moo_init --bootstrap zork2 --sync`` which re-executes the
    generated ``099_reset_state.py`` (snapshot restore + canonical item
    placement).  Celery is stopped for the duration so a live daemon tick
    can't deadlock the single-transaction sync, then restarted.
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
                f"/usr/app/bin/python /usr/app/src/manage.py moo_init --bootstrap zork2 --sync --hostname {hostname}",
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    finally:
        subprocess.run(["docker", "start", _CELERY], capture_output=True, text=True, timeout=60, check=False)


# (command, substring expected in output, or None to just print + skip the
# assertion).  Every assertion below was verified live on 2026-06-04.
ZORK2_COMMANDS = [
    ("look", "Inside the Barrow"),  # opening room, correctly lit
    ("inventory", "empty-handed"),  # start empty — items on the floor
    ("take lamp", "Taken"),
    ("take sword", "Taken"),
    ("turn on lamp", "now on"),  # "The lamp is now on."
    ("examine sword", "nothing special"),  # generic examine fallback
    ("south", "Narrow Tunnel"),
    ("south", "Foot Bridge"),
    ("south", "Great Cavern"),
    ("east", "can't go that way"),  # fail-probe: Great Cavern has only SW/NE
    ("southwest", "Shallow Ford"),
    ("south", "Dark Tunnel"),
    ("southwest", "Path Near Stream"),
    ("drop sword", "Dropped"),  # idrop (shared g-verb helper)
    ("take sword", "Taken"),
    ("east", "Formal Garden"),
    ("inventory", "sword"),  # still carrying lamp + sword
    # --- Formal Garden side-trips: structure (N) and topiary (S) ---
    ("north", "North End of Garden"),  # the unicorn bounds lightly away on entry
    ("south", "Formal Garden"),
    ("south", "Topiary"),  # hedge-creature garden
    ("north", "Formal Garden"),
    # --- Carousel Room: deterministic now that CAROUSEL-FLIP-FLAG is seeded ---
    ("west", "Path Near Stream"),
    ("southwest", "Carousel Room"),  # stopped: no "disoriented" whirring line
    ("north", "Marble Hall"),  # the stopped spin routes N reliably
    ("south", "Carousel Room"),
    ("north", "Marble Hall"),  # same exit again → proves determinism
    # --- beyond Marble Hall: the ravine, then the dragon (a major NPC) ---
    ("north", "Deep Ford"),  # fording the cold stream
    ("north", "Ledge in Ravine"),
    ("west", "End of Ledge"),  # smokey tunnel N toward the dragon
    ("north", "Dragon Room"),
    ("examine dragon", "weak"),  # DRAGON-FCN gaze weakens you (npc_atom_map)
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the zork2 smoke test.")
    parser.add_argument(
        "--hostname",
        default="zork2.local",
        help="Site domain (used as the ``phil+<host>`` SSH user). Default: zork2.local.",
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
    _reset_zork2_state(hostname=hostname)

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
        for cmd, expected in ZORK2_COMMANDS:
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
    print(f"PASS ({len(ZORK2_COMMANDS)} commands)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
