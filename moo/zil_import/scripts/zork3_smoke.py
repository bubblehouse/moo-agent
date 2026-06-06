#!/usr/bin/env python3
"""End-to-end smoke test for the zil_import-generated Zork III bootstrap.

Connects to the live ``zork3.local`` universe over SSH and walks the
canonical opening of Zork III, asserting that:

- the post-auth ``Connected to universe: zork3.local`` banner was emitted
- the session opens on the ``Endless Stair`` (lit; carrying nothing)
- core verbs fire correctly: ``inventory`` / ``diagnose`` / ``score`` /
  ``examine`` / ``wait``, plus the ``take``-the-embedded-sword special case
- the deterministic movement spine works and a blocked exit fails cleanly

The walk threads both shakedown branches into one continuous path: down the
western spur (Junction → Barren Area → Cliff, with the sword embedded in the
great rock at the Junction and the reverse Cliff→Barren→Junction exits), then
the southern dungeon (Creepy Crawl → Tight Squeeze → Crystal Grotto, back,
then SW into the Land of Shadow → Foggy Room → Lake Shore → Aqueduct View).
Extend the command list room-by-room as later puzzles are mapped and verified
live (the hooded-figure combat, the Lake/chest swim puzzle, the Scenic Vista
time-travel mechanic — see the zork3-shakedown skill).

Lives under ``scripts/`` (not ``tests/``) so pytest doesn't try to import it
— it requires a live SSH server + docker-compose stack.

Run::

    uv run python -m moo.zil_import.scripts.zork3_smoke 2>&1 | tee /tmp/smoke.out
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


def _reset_zork3_state(hostname: str = "zork3.local") -> None:
    """Re-sync the world to its canonical opening (Celery stopped meanwhile).

    Runs ``moo_init --bootstrap zork3 --sync`` which re-executes the
    generated ``099_reset_state.py`` (snapshot restore + canonical avatar
    placement at the Endless Stair).  Celery is stopped for the duration so
    a live daemon tick can't deadlock the single-transaction sync, then
    restarted.
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
                f"/usr/app/bin/python /usr/app/src/manage.py moo_init --bootstrap zork3 --sync --hostname {hostname}",
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    finally:
        subprocess.run(["docker", "start", _CELERY], capture_output=True, text=True, timeout=60, check=False)


# (command, substring expected in output, or None to just print + skip the
# assertion).  Every assertion below was verified live on 2026-06-05/06.
ZORK3_COMMANDS = [
    ("look", "Endless Stair"),  # opening room, correctly lit
    ("inventory", "empty-handed"),  # Zork III opens carrying nothing
    ("diagnose", "perfect health"),  # DIAG[P-STRENGTH=5] (zork3 diagnose shim)
    ("score", "of a possible 7"),  # Zork III max score is 7, not 350
    ("down", "can't go that way"),  # fail-probe: Endless Stair only exits S/up
    ("south", "Junction"),
    # The sword is embedded in the great rock here — can't be taken yet.
    ("take sword", "imbedded"),  # "deeply imbedded in the rock. You can't budge it."
    # --- western spur: Barren Area + Cliff, with verified reverse exits ---
    ("west", "Barren Area"),
    ("west", "Cliff"),
    ("examine rope", "nothing special"),  # generic examine fallback
    ("east", "Barren Area"),  # reverse exit
    ("east", "Junction"),  # reverse exit (back to the hub)
    # --- southern dungeon spine ---
    ("south", "Creepy Crawl"),
    ("east", "Tight Squeeze"),
    ("east", "Crystal Grotto"),
    ("west", "Tight Squeeze"),
    ("west", "Creepy Crawl"),
    ("southwest", "Land of Shadow"),  # footsteps nearby (hooded-figure daemon)
    ("southeast", "Foggy Room"),
    ("south", "Lake Shore"),
    ("swim", "Go jump in a lake"),  # canonical SWIM refusal
    ("southeast", "Aqueduct View"),
    ("wait", "Time passes"),  # clocker shim — no crash
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the zork3 smoke test.")
    parser.add_argument(
        "--hostname",
        default="zork3.local",
        help="Site domain (used as the ``phil+<host>`` SSH user). Default: zork3.local.",
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
    _reset_zork3_state(hostname=hostname)

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
        for cmd, expected in ZORK3_COMMANDS:
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
    print(f"PASS ({len(ZORK3_COMMANDS)} commands)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
