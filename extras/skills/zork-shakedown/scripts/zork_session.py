#!/usr/bin/env python3
"""
Long-lived MooSSH session harness for the zork-shakedown skill.

Holds a single SSH connection to ``zork1.local`` open for the duration of a
shake-down session.  The harness reads commands from a FIFO and appends
PREFIX/SUFFIX-delimited responses to a log file, so the driving caller
(Claude) can issue commands one at a time across multiple Bash invocations
without paying the cost of reconnecting between turns.

Subcommands::

    zork_session.py start [--reset] [--user U] [--password P]
        Connect, optionally re-sync the world (resets to canonical opening
        positions), and daemonize.  Idempotent on stale state — clears any
        previous PID/FIFO/log files.

    zork_session.py send <command>
        Send one Zork (or shell) command to the running session.  Returns
        immediately; output is appended to the log.

    zork_session.py read [--tail N]
        Print the session log (or the last N lines).

    zork_session.py since <marker>
        Print the log starting from the most recent occurrence of ``>>>
        <marker>`` — convenient for "show me everything after the last
        ``look`` I sent."

    zork_session.py stop
        Send ``:quit`` to the harness; harness disconnects MooSSH cleanly
        and exits.

    zork_session.py status
        Print "running (pid N)" or "not running".

The harness is single-threaded and synchronous: ``moo.run(cmd)`` blocks
until the command's response arrives, so back-to-back ``send`` calls queue
naturally on the FIFO.

Run this script directly via ``Bash run_in_background: true`` so the parent
turn doesn't block on the start subcommand.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import subprocess
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
# moo_ssh.py lives in the sibling game-designer skill under
# moo-agent/extras/skills/.  SCRIPT_DIR is .../zork-shakedown/scripts/,
# so two parents up lands in extras/skills/.
_MOO_SSH_PATH = SCRIPT_DIR.parent.parent / "game-designer" / "tools" / "moo_ssh.py"
if not _MOO_SSH_PATH.exists():
    print(f"Could not find moo_ssh.py at {_MOO_SSH_PATH}", file=sys.stderr)
    sys.exit(2)
_spec = importlib.util.spec_from_file_location("moo_ssh", _MOO_SSH_PATH)
_moo_ssh = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_moo_ssh)
MooSSH = _moo_ssh.MooSSH

# Use /tmp paths so the files are easy to find and survive reboot.
FIFO_PATH = Path("/tmp/zork-shakedown.fifo")
LOG_PATH = Path("/tmp/zork-shakedown.log")
PID_PATH = Path("/tmp/zork-shakedown.pid")

DEFAULT_USER = "phil+zork1.local"
DEFAULT_PASSWORD = "qw12er34"  # nosec B105 — dev/test password documented in SOUL


def _ts() -> str:
    return time.strftime("%H:%M:%S")


def _is_running() -> int | None:
    if not PID_PATH.exists():
        return None
    try:
        pid = int(PID_PATH.read_text(encoding="utf-8").strip())
        os.kill(pid, 0)
        return pid
    except (ValueError, OSError):
        return None


def cmd_start(args: argparse.Namespace) -> int:
    pid = _is_running()
    if pid is not None:
        print(f"Session already running (pid {pid}). Run 'stop' first.", file=sys.stderr)
        return 1
    # Clean up stale files from a crashed prior run
    for p in (FIFO_PATH, PID_PATH):
        try:
            p.unlink()
        except FileNotFoundError:
            pass

    if args.reset:
        # World reset — bootstrap-on-sync pattern; re-runs all numbered
        # bootstrap scripts including 099_reset_state.py.
        #
        # moo_init wraps the whole bootstrap in a single transaction.
        # atomic().  If a live Celery daemon tick (i_thief, i_forest_room,
        # …) touches the same Object/Property rows mid-sync, Postgres
        # deadlocks and the ENTIRE reset rolls back — silently leaving the
        # world in its prior state (stale deaths/score/inventory, wrench
        # in the thief, …).  Stop the Celery worker for the duration of
        # the sync so there is no competing writer, then restart it.
        print(f"[{_ts()}] resetting world state on zork1.local...", flush=True)
        _celery = "django-moo-celery-1"
        subprocess.run(["docker", "stop", _celery], capture_output=True, text=True, timeout=60, check=False)
        try:
            result = subprocess.run(
                [
                    "docker",
                    "exec",
                    "django-moo-shell-1",
                    "sh",
                    "-c",
                    "/usr/app/bin/python /usr/app/src/manage.py moo_init --bootstrap zork1 --sync --hostname zork1.local",
                ],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
        finally:
            # Always bring Celery back, even if the sync raised — the
            # daemons are required for a playable session.
            subprocess.run(["docker", "start", _celery], capture_output=True, text=True, timeout=60, check=False)
        if result.returncode != 0:
            print(f"[{_ts()}] reset failed: {result.stderr}", file=sys.stderr)
            return 1
        if "deadlock detected" in (result.stdout + result.stderr):
            print(f"[{_ts()}] reset failed: deadlock detected despite Celery stop", file=sys.stderr)
            return 1

    os.mkfifo(FIFO_PATH)
    log_fp = open(LOG_PATH, "w", encoding="utf-8")  # noqa: SIM115 — long-lived
    PID_PATH.write_text(str(os.getpid()), encoding="utf-8")

    log_fp.write(f"[{_ts()}] starting zork-shakedown session as {args.user}\n")
    log_fp.flush()

    moo = MooSSH(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        timeout=args.timeout,
        verbose=False,
    )
    try:
        moo.connect()
        moo.enable_delimiters()
    except Exception as e:  # pylint: disable=broad-exception-caught
        log_fp.write(f"[{_ts()}] connect failed: {type(e).__name__}: {e}\n")
        log_fp.flush()
        log_fp.close()
        PID_PATH.unlink(missing_ok=True)
        FIFO_PATH.unlink(missing_ok=True)
        return 1
    log_fp.write(f"[{_ts()}] connected to universe: zork1.local\n")
    log_fp.flush()

    try:
        # Re-open the FIFO every time the writer closes — that's the
        # canonical FIFO read loop.  Each `send` opens, writes, closes,
        # giving us EOF and a fresh open() on the next iteration.
        while True:
            with open(FIFO_PATH, "r", encoding="utf-8") as fifo:
                for line in fifo:
                    cmd = line.rstrip("\n").strip()
                    if not cmd:
                        continue
                    if cmd in (":quit", ":stop"):
                        log_fp.write(f"[{_ts()}] :quit received, stopping\n")
                        log_fp.flush()
                        return 0
                    log_fp.write(f"\n[{_ts()}] >>> {cmd}\n")
                    log_fp.flush()
                    started = time.time()
                    try:
                        out = moo.run(cmd)
                    except Exception as e:  # pylint: disable=broad-exception-caught
                        out = f"[harness] error: {type(e).__name__}: {e}"
                    elapsed = time.time() - started
                    log_fp.write(f"{out}\n")
                    log_fp.write(f"[{_ts()}] (took {elapsed:.1f}s)\n")
                    log_fp.flush()
    finally:
        try:
            moo.run("@quit")
        except Exception:  # pylint: disable=broad-exception-caught
            pass
        try:
            moo.disconnect()
        except Exception:  # pylint: disable=broad-exception-caught
            pass
        log_fp.write(f"[{_ts()}] session closed\n")
        log_fp.close()
        PID_PATH.unlink(missing_ok=True)
        FIFO_PATH.unlink(missing_ok=True)
    return 0


def cmd_send(args: argparse.Namespace) -> int:
    if _is_running() is None:
        print("No session running. Run 'start' first.", file=sys.stderr)
        return 1
    # Open and close the FIFO for each line so the harness's read loop
    # gets a clean EOF and re-opens on the next iteration.
    with open(FIFO_PATH, "w", encoding="utf-8") as fifo:
        fifo.write(args.command + "\n")
    return 0


def cmd_read(args: argparse.Namespace) -> int:
    if not LOG_PATH.exists():
        print("No log yet (start a session first).", file=sys.stderr)
        return 1
    text = LOG_PATH.read_text(encoding="utf-8")
    if args.tail is not None:
        lines = text.splitlines()
        text = "\n".join(lines[-args.tail :])
    sys.stdout.write(text)
    if not text.endswith("\n"):
        sys.stdout.write("\n")
    return 0


def cmd_since(args: argparse.Namespace) -> int:
    if not LOG_PATH.exists():
        print("No log yet (start a session first).", file=sys.stderr)
        return 1
    marker = f">>> {args.marker}"
    lines = LOG_PATH.read_text(encoding="utf-8").splitlines()
    # Find the LAST line containing the marker so successive ``since look``
    # calls show only the freshest ``look`` output.
    last_idx = None
    for i, line in enumerate(lines):
        if marker in line:
            last_idx = i
    if last_idx is None:
        print(f"Marker '{args.marker}' not found in log.", file=sys.stderr)
        return 1
    sys.stdout.write("\n".join(lines[last_idx:]) + "\n")
    return 0


def cmd_stop(_args: argparse.Namespace) -> int:
    if _is_running() is None:
        print("No session running.", file=sys.stderr)
        return 0
    with open(FIFO_PATH, "w", encoding="utf-8") as fifo:
        fifo.write(":quit\n")
    # Give the harness a moment to disconnect cleanly.
    for _ in range(10):
        if _is_running() is None:
            break
        time.sleep(0.5)
    return 0


def cmd_status(_args: argparse.Namespace) -> int:
    pid = _is_running()
    if pid is not None:
        print(f"running (pid {pid})")
    else:
        print("not running")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="zork_session")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_start = sub.add_parser("start", help="Connect and daemonize.")
    p_start.add_argument("--user", default=DEFAULT_USER)
    p_start.add_argument("--password", default=DEFAULT_PASSWORD)
    p_start.add_argument("--host", default="localhost")
    p_start.add_argument("--port", type=int, default=8022)
    p_start.add_argument("--timeout", type=float, default=10.0)
    p_start.add_argument(
        "--reset",
        action="store_true",
        help="Run moo_init --sync first to reset world state to opening positions.",
    )

    p_send = sub.add_parser("send", help="Send one command.")
    p_send.add_argument("command")

    p_read = sub.add_parser("read", help="Print the session log.")
    p_read.add_argument("--tail", type=int, default=None)

    p_since = sub.add_parser(
        "since",
        help="Print log since the most recent occurrence of '>>> <marker>'.",
    )
    p_since.add_argument("marker")

    sub.add_parser("stop", help="Cleanly close the session.")
    sub.add_parser("status", help="Print 'running (pid N)' or 'not running'.")

    args = parser.parse_args()
    handler = {
        "start": cmd_start,
        "send": cmd_send,
        "read": cmd_read,
        "since": cmd_since,
        "stop": cmd_stop,
        "status": cmd_status,
    }[args.cmd]
    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
