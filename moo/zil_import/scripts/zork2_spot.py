#!/usr/bin/env python3
"""Run a short scripted command sequence against the live zork2 universe.

The fast iterative-debugging tool for the zork2 translator/generator fix
loop: connect to ``zork2.local`` over SSH and run whatever commands the
caller passes, printing output verbatim (for human eyes, not assertion).

``--reset`` re-syncs the world to its canonical opening first (stops the
Celery worker for the duration so a live daemon tick can't deadlock the
sync transaction, then restarts it) — the same pattern the long-lived
``zork2_session.py`` harness uses.

Usage::

    uv run python -m moo.zil_import.scripts.zork2_spot \\
        "look" "south" "north" "take lantern" "turn on lantern"

    uv run python -m moo.zil_import.scripts.zork2_spot --reset \\
        "look" "south"

A full canonical opener-smoke (the assertion-driven ``zork2_smoke.py``)
does not exist yet — it's the deliverable of the first dedicated zork2
shakedown session, which maps the canonical walkthrough.  Until then this
spot script plus the connected ``zork2_session.py`` harness are the
verification tools.
"""

from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys
from pathlib import Path

# ``moo_ssh`` lives in the game-designer toolbox.  The skills moved into
# moo-agent (ea2ffce7), so prefer the in-repo copy and fall back to the
# django-moo sibling checkout for older layouts.
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

_CELERY = "django-moo-celery-1"
_SHELL = "django-moo-shell-1"


def _reset_zork2_state() -> None:
    """Re-sync zork2.local to its canonical opening (Celery stopped meanwhile)."""
    subprocess.run(["docker", "stop", _CELERY], capture_output=True, text=True, timeout=60, check=False)
    try:
        result = subprocess.run(
            [
                "docker",
                "exec",
                _SHELL,
                "sh",
                "-c",
                "/usr/app/bin/python /usr/app/src/manage.py moo_init --bootstrap zork2 --sync --hostname zork2.local",
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    finally:
        subprocess.run(["docker", "start", _CELERY], capture_output=True, text=True, timeout=60, check=False)
    if result.returncode != 0:
        print(f"[spot] reset failed: {result.stderr}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", maxsplit=1)[0])
    parser.add_argument("commands", nargs="+", help="MOO commands to send, in order")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Reset world state to the canonical opening before connecting",
    )
    args = parser.parse_args()

    if args.reset:
        print("[spot] resetting zork2 world state ...", flush=True)
        _reset_zork2_state()

    with MooSSH(
        host="localhost",
        port=8022,
        user="phil+zork2.local",
        password="qw12er34",  # nosec B106 — dev/test password
        timeout=10,
        verbose=False,
    ) as moo:
        moo.enable_delimiters()
        for cmd in args.commands:
            out = moo.run(cmd)
            print(f">>> {cmd}\n{out}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
