#!/usr/bin/env python3
"""Run a short scripted command sequence against the live zork1 universe.

Faster sibling to ``zork1_smoke``: the smoke walks the canonical 350-command
opener and takes ~70s; this script runs whatever the caller passes on the
command line, skipping the world-reset by default so iterative debugging
(``go north`` → ``open trap door`` → expected output``) doesn't pay the
reset cost twice.

Usage:

    uv run python -m moo.zil_import.scripts.zork1_spot \\
        "go north" "go east" "go west" "go west" "open trap door"

    # add --reset to start from the canonical opening state
    uv run python -m moo.zil_import.scripts.zork1_spot --reset \\
        "go north" "open trap door"

Output is printed verbatim — the script is for human eyes, not assertion.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

_DJANGO_MOO_ROOT = Path(__file__).resolve().parents[3].parent / "django-moo"
_MOO_SSH_PATH = _DJANGO_MOO_ROOT / "extras" / "skills" / "game-designer" / "tools" / "moo_ssh.py"
_spec = importlib.util.spec_from_file_location("moo_ssh", _MOO_SSH_PATH)
_moo_ssh = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_moo_ssh)
MooSSH = _moo_ssh.MooSSH

# Reuse the smoke's reset helper rather than duplicate the snippet.
_smoke_path = Path(__file__).with_name("zork1_smoke.py")
_smoke_spec = importlib.util.spec_from_file_location("zork1_smoke", _smoke_path)
_smoke = importlib.util.module_from_spec(_smoke_spec)
_smoke_spec.loader.exec_module(_smoke)


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
        print("[spot] resetting zork1 world state ...", flush=True)
        _smoke._reset_zork1_state()  # pylint: disable=protected-access

    with MooSSH(
        host="zork1.local",
        port=8022,
        user="phil+zork1.local",
        password="qw12er34",
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
