"""CLI wrapper for the Zork 1 world-state reset snippet.

Replaces the moo-core ``moo_reset`` management command (which was reverted
under Rule Zero — Zork-specific commands belong here, not in
``moo/core/management/commands/``).

Reuses ``_RESET_SNIPPET`` from ``zork1_smoke`` so the operator and the
smoke test always run the exact same reset.

Usage::

    uv run python -m extras.zil_import.scripts.zork1_reset
    uv run python -m extras.zil_import.scripts.zork1_reset --hostname zork1.local
"""

import argparse
import subprocess
import sys
from pathlib import Path

from extras.zil_import.scripts.zork1_smoke import _REPO_ROOT, _RESET_SNIPPET


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset zork1.local world state.")
    parser.add_argument(
        "--hostname",
        default="zork1.local",
        help="Site domain to reset (default: zork1.local).",
    )
    args = parser.parse_args()

    snippet = _RESET_SNIPPET
    if args.hostname != "zork1.local":
        # The shipped snippet hard-codes ``zork1.local``; rewrite for
        # operators running against a non-default site.
        snippet = snippet.replace("'zork1.local'", repr(args.hostname))

    print(f"[zork1_reset] resetting world state on {args.hostname} ...", flush=True)
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
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
