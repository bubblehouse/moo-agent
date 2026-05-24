#!/usr/bin/env python3
"""
moo_run.py - Send arbitrary commands to a DjangoMOO server and print results.

Commands can be passed as arguments, piped via stdin, or read from a file.
Each command is sent in order; output is printed after each one.

Usage:
    python moo_run.py "look" "@survey" "@divine location"
    echo "look" | python moo_run.py
    python moo_run.py --file cmds.txt
    python moo_run.py --host localhost --port 8022 "look"
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from moo_ssh import MooSSH  # pylint: disable=wrong-import-position


def main():
    parser = argparse.ArgumentParser(description="Send commands to a DjangoMOO server via SSH.")
    parser.add_argument("commands", nargs="*", help="Commands to run (in order)")
    parser.add_argument("--file", "-f", metavar="FILE", help="Read commands from a file (one per line)")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=8022)
    args = parser.parse_args()

    # Collect commands from args, file, or stdin
    commands = list(args.commands)

    if args.file:
        lines = Path(args.file).read_text(encoding="utf-8").splitlines()
        commands += [l for l in lines if l.strip() and not l.startswith("#")]

    if not commands and not sys.stdin.isatty():
        commands += [l for l in sys.stdin.read().splitlines() if l.strip() and not l.startswith("#")]

    if not commands:
        parser.print_help()
        sys.exit(1)

    with MooSSH(host=args.host, port=args.port) as moo:
        moo.enable_automation_mode()
        for cmd in commands:
            print(f">>> {cmd}")
            result = moo.run(cmd)
            print(result)
            print()


if __name__ == "__main__":
    main()
