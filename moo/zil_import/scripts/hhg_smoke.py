#!/usr/bin/env python3
"""End-to-end smoke test for the zil_import-generated HHG bootstrap.

Connects to the live ``hhg.local`` universe over SSH using the
``user+sitedomain`` multi-universe routing suffix, walks the canonical
opening of The Hitchhiker's Guide to the Galaxy, and asserts that the full
"natural" solve runs end-to-end:

- the post-auth banner ``Connected to universe: hhg.local`` was emitted
- the bedroom opener renders and ``wear gown`` works
- ``block bulldozer`` stops the demolition and Ford takes you to the Pub
- three beers + the Vogon fleet + the green button hitch a ride off Earth
- the Dark puzzle (smell → shadow → examine) lands you in the Vogon Hold
- the protein-loss timer is survived by eating the peanuts
- Ford's I-FORD nap drops the satchel, and the babel-fish puzzle solves
  (gown on hook, towel on drain, satchel in front of panel, mail on satchel,
  push button → the fish lands "squish" in your ear)
- the Vogon act runs to completion on ``wait`` turns: the poetry trial, the
  airlock, ejection into space, and rescue by the passing Heart of Gold

This is the HHG counterpart to ``zork1_smoke.py`` and the standing regression
guard for the canonical path verified on 2026-05-30.  Lives under ``scripts/``
rather than ``tests/`` so pytest's auto-discovery doesn't try to import it as
a unit test (it requires a live SSH server and docker-compose stack).

Run:

    uv run python -m moo.zil_import.scripts.hhg_smoke 2>&1 | tee /tmp/hhg_smoke.out
"""

from __future__ import annotations

import importlib.util
import io
import subprocess
import sys
import time
from pathlib import Path

# ``moo_ssh`` lives in the game-designer toolbox and isn't a normal Python
# package (the parent dir name has a hyphen).  Walk up from this script to
# find it by file path — same shim as zork1_smoke.py.
_MOO_AGENT_ROOT = Path(__file__).resolve().parents[3]
_DJANGO_MOO_ROOT = _MOO_AGENT_ROOT.parent / "django-moo"
_MOO_SSH_PATH = _MOO_AGENT_ROOT / "extras" / "skills" / "game-designer" / "tools" / "moo_ssh.py"
if not _MOO_SSH_PATH.exists():
    _MOO_SSH_PATH = _DJANGO_MOO_ROOT / "extras" / "skills" / "game-designer" / "tools" / "moo_ssh.py"
_spec = importlib.util.spec_from_file_location("moo_ssh", _MOO_SSH_PATH)
_moo_ssh = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_moo_ssh)
MooSSH = _moo_ssh.MooSSH
strip_ansi = _moo_ssh.strip_ansi


_CELERY_CONTAINER = "django-moo-celery-1"
_SHELL_CONTAINER = "django-moo-shell-1"


def _reset_hhg_state(hostname: str = "hhg.local") -> None:
    """Reset the HHG world to its canonical opening positions.

    Mirrors ``hhg_session.py --reset``: stop the Celery worker (so a live
    daemon tick can't deadlock the single-transaction ``moo_init`` sync and
    silently roll the whole reset back), re-run the bootstrap sync (which
    re-runs ``099_reset_state.py``), then restart Celery.  Idempotent.
    """
    subprocess.run(
        ["docker", "stop", _CELERY_CONTAINER],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    try:
        result = subprocess.run(
            [
                "docker",
                "exec",
                _SHELL_CONTAINER,
                "sh",
                "-c",
                f"/usr/app/bin/python /usr/app/src/manage.py moo_init --bootstrap hhg --sync --hostname {hostname}",
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    finally:
        subprocess.run(
            ["docker", "start", _CELERY_CONTAINER],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    if result.returncode != 0:
        raise RuntimeError(f"hhg reset failed: {result.stderr}")
    if "deadlock detected" in (result.stdout + result.stderr):
        raise RuntimeError("hhg reset failed: deadlock detected despite Celery stop")


# Sentinel commands (``__name__``) run a Python helper that drives several
# real MOO commands — used for the timing-sensitive beats (queued daemons:
# the bulldozer/Ford handover, the I-VOGONS fleet, the I-FORD satchel drop)
# where a fixed ``wait`` count is fragile.  Each helper returns the output
# text used for the tuple's substring assertion.
#
# (command, expected substring in output, or None to send + skip the check).
HHG_COMMANDS = [
    # --- Bedroom: the canonical opener ---
    ("look", "Bedroom"),
    ("wear gown", "wearing"),
    ("south", "Front Porch"),
    ("south", "Front of House"),
    # --- Bulldozer: lie down in its path; Ford arrives and swaps in Prosser ---
    ("block bulldozer", "lie down in the path"),
    ("__wait_for_ford__", "stand up"),
    ("take towel", "Taken"),
    ("south", "Country Lane"),
    ("west", "Pub"),  # Ford buys lots of beer
    ("drink beer", None),
    ("drink beer", None),
    ("drink beer", None),  # DRUNK-LEVEL 3 — survive the matter transference
    ("east", "Country Lane"),
    # --- Vogon fleet arrives; hitch a ride with the green button ---
    ("__escape_earth__", "Lights whirl"),
    # --- The Dark: sense your way to the Vogon Hold ---
    ("__leave_dark__", "Vogon Hold"),
    # --- Vogon Hold: eat the peanuts before the protein-loss timer kills you ---
    ("__eat_peanuts__", "stronger"),
    # --- Babel-fish puzzle: Ford naps and drops the satchel (I-FORD) ---
    ("__wait_for_satchel__", "Taken"),
    ("remove gown", None),
    ("put gown on hook", "hanging from the hook"),
    ("put towel on drain", "covers the drain"),
    ("put satchel in front of panel", "in front of"),
    ("put mail on satchel", "on the satchel"),
    ("push button", "squish"),  # the babel fish lands in your ear
    # --- Vogon act: poetry trial -> airlock -> ejected into space -> rescued ---
    # I-GUARDS drags you to the poetry chairs, I-CAPTAIN reads the verse (you
    # didn't enjoy it, so at CAPTAIN-COUNTER 6 the guards toss you out), I-FORD
    # stalls the guard in the Hold (GUARDS-COUNTER 1->6), then AIRLOCK-F ejects
    # you into space (AIRLOCK-COUNTER 1->4) where the Heart of Gold scoops you up.
    ("__survive_vogons__", "scooped up"),
    # --- Post-airlock Dark -> Entry Bay -> Heart of Gold bridge ---
    # listen for the star drive (DARK-COUNTER > 3), `go south` into the Entry
    # Bay, then wait for I-FORD to walk you up to the Bridge.
    ("__reach_heart_of_gold__", "Bridge"),
    # --- Engine Room: reveal and take the spare Improbability Drive ---
    # Down to the corridors, through the Aft Corridor's SOUTH persistence gate
    # (ARGUMENT-COUNTER > 4), then `look` x3 (LOOK-COUNTER >= 3) to reveal the
    # spare drive / pliers / rasp, and take the drive.
    ("__take_spare_drive__", "Taken"),
    # --- Bridge: plug the spare drive into the manual-override receptacle ---
    # Back up to the Bridge and plug the large plug into the large receptacle
    # (sets DRIVE-TO-CONTROLS — the deepest verified beat on the win path).
    ("__plug_drive__", "Plugged"),
    # NB: `turn on spare drive` now correctly reaches SPARE-DRIVE-F's lamp_on
    # branch (the `light` -> `lamp_on` object-function atom fix, completed-work
    # 2026-06-02) — but it can't yet complete: SPARE-DRIVE-F's
    # `perform(lamp_on, lookup('switch'))` resolves to a *dipswitch* (the
    # `switch` atom collides with the dipswitches' SYNONYM SWITCH), so the
    # generator switch never fires.  See BUGS.md (zatom collision).  No smoke
    # assertion here until that's fixed.
]


def _wait_for_ford(moo) -> str:
    """``wait`` until Prosser takes over and you stand up (Ford handover)."""
    acc = ""
    for _ in range(10):
        out = moo.run("wait")
        print(f">>> 'wait' (for-ford)\n{out}\n", flush=True)
        acc += "\n" + out
        if "stand up" in out.lower() or "lies down in front" in out.lower():
            break
    return acc


def _escape_earth(moo) -> str:
    """Hitch a ride off Earth the instant the Vogon fleet drops the device.

    The I-VOGONS demolition daemon is on a tight counter: the Sub-Etha device
    drops "at your feet" at VOGON-COUNTER 2 and the Earth is destroyed at
    VOGON-COUNTER 5, so there are only ~2 turns to ``take device`` + ``push
    green button``.  Crucially we poll on game *state* (is the device takeable
    yet?) rather than on the daemon's *text*: async daemon output is framed a
    turn or two behind the command that triggered it (the moo-core PREFIX/SUFFIX
    side-channel lag), so waiting for the "at your feet" string lands us a turn
    late and the demolition fires first.  ``take device`` doubles as the per-turn
    wait — it fails (consuming the turn) until the device is on the ground, then
    succeeds, and we push immediately.  ``wait`` is what advances the clock —
    a failed ``take device`` (no device on the ground yet) is parser-rejected
    and does NOT tick the daemon, so each turn must be advanced with ``wait``.
    """
    push = ""
    for _ in range(20):
        w = moo.run("wait")
        print(f">>> 'wait' (await fleet)\n{w}\n", flush=True)
        take = moo.run("take device")
        print(f">>> 'take device' (poll)\n{take}\n", flush=True)
        if "taken" in take.lower():
            push = moo.run("push green button")
            print(f">>> 'push green button'\n{push}\n", flush=True)
            break
    return push


def _leave_dark(moo) -> str:
    """Sense your way out of the Dark into the Vogon Hold.

    A bare ``smell`` first clears your head; then ``smell darkness`` reveals a
    shadow, and ``examine shadow`` triggers LEAVE-DARK into the destination
    room (the Vogon Hold, since the green-button escape set DARK-FLAG=HOLD).
    """
    out = moo.run("smell")
    print(f">>> 'smell' (clear head)\n{out}\n", flush=True)
    for _ in range(6):
        out = moo.run("smell darkness")
        print(f">>> 'smell darkness'\n{out}\n", flush=True)
        if "shadow" in out.lower():
            break
    examine = moo.run("examine shadow")
    print(f">>> 'examine shadow'\n{examine}\n", flush=True)
    return examine


def _eat_peanuts(moo) -> str:
    """Wait for the Hold M-END to hand over the peanuts, then eat them.

    HOLD-F's M-END (which gives the peanuts and arms the I-GROGGY protein-loss
    timer) fires at the end of the first full turn in the Hold, so the peanuts
    aren't in scope on the arrival turn.  Spend filler turns until the handover
    fires, then eat — well within the ~5-turn I-GROGGY death window.  Poll on
    state (does ``eat peanuts`` succeed?) rather than the handover text, which
    lags behind the turn that produced it.
    """
    eat = ""
    for _ in range(5):
        eat = moo.run("eat peanuts")
        print(f">>> 'eat peanuts' (poll)\n{eat}\n", flush=True)
        if "stronger" in eat.lower():
            break
        w = moo.run("wait")
        print(f">>> 'wait' (await peanuts)\n{w}\n", flush=True)
    return eat


def _wait_for_satchel(moo) -> str:
    """``wait`` for Ford's I-FORD nap to drop the satchel, then take it.

    HOLD-F's M-END queues I-FORD ~6 turns out; when it fires Ford naps and
    drops the satchel into the Hold with TRYTAKEBIT cleared.  Poll by trying
    ``take satchel`` after each ``wait`` so we're robust to the exact tick.
    """
    take = ""
    for _ in range(10):
        take = moo.run("take satchel")
        print(f">>> 'take satchel'\n{take}\n", flush=True)
        if "taken" in take.lower():
            break
        w = moo.run("wait")
        print(f">>> 'wait' (for-satchel)\n{w}\n", flush=True)
    return take


def _survive_vogons(moo) -> str:
    """``wait`` through the Vogon poetry trial and out the airlock into space.

    After the babel fish, an unbroken daemon chain runs purely on ``wait``
    turns: I-GUARDS drags you to the poetry-appreciation chairs in the
    Captain's Quarters, I-CAPTAIN reads the verse (you didn't enjoy it, so
    at CAPTAIN-COUNTER 6 the captain has the guards toss you out), I-FORD
    stalls the guard in the Hold (GUARDS-COUNTER 1->6) then throws you into
    the airlock, and AIRLOCK-F's M-END counts 1->4 before blowing you into
    space, where you're scooped up by a passing ship (the Heart of Gold).

    This is the beat that the ``goto`` VTYPE-gate fix unblocks: the player
    must be relocated *out* of the strapped-in poetry chair (a VEHBIT object
    with no VTYPE) into the Hold and then the Airlock as a direct occupant,
    or AIRLOCK-F's M-END never ticks and the ejection never fires.  Poll on
    the ejection text rather than a fixed wait count — the chain spans ~16
    turns and the intercom noise makes the cadence hard to predict.
    """
    acc = ""
    for _ in range(40):
        out = moo.run("wait")
        print(f">>> 'wait' (survive-vogons)\n{out}\n", flush=True)
        acc += "\n" + out
        if "scooped up" in out.lower():
            break
    return acc


def _reach_heart_of_gold(moo) -> str:
    """From the post-airlock Dark, ride the Heart of Gold up to the Bridge.

    ``__survive_vogons__`` leaves you in the Dark (DARK-FLAG=ENTRY-BAY) after
    the rescue.  ``listen`` reveals the star-drive hum once DARK-COUNTER > 3 (a
    couple of turns), ``go south`` emerges into Entry Bay Number Two, then
    I-FORD's HEART-COUNTER ticks on each ``wait`` until it walks you and Ford up
    to the Bridge.  Poll on the room text rather than a fixed count — the
    intercom noise makes the cadence hard to predict.
    """
    out = ""
    for _ in range(8):
        out = moo.run("listen")
        print(f">>> 'listen' (for-star-drive)\n{out}\n", flush=True)
        if "star drive" in out.lower():
            break
    south = moo.run("go south")
    print(f">>> 'go south' (emerge)\n{south}\n", flush=True)
    acc = south
    for _ in range(8):
        out = moo.run("wait")
        print(f">>> 'wait' (for-bridge)\n{out}\n", flush=True)
        acc += "\n" + out
        if "bridge" in out.lower():
            break
    return acc


def _take_spare_drive(moo) -> str:
    """Descend to the Engine Room, reveal the spare drive, and take it.

    Bridge ``down`` -> Fore Corridor, ``south`` -> Aft Corridor, whose SOUTH is
    a persistence gate (each ``south`` bumps ARGUMENT-COUNTER and re-arms the
    i-argument abort daemon; you enter the Engine Room at counter > 4, so send
    ``south`` until the room renders).  ENGINE-ROOM-F hides its contents until
    the third M-LOOK (LOOK-COUNTER >= 3 reveals the spare drive / pliers / rasp
    and awards +25), so ``look`` until the spare drive appears, then take it.
    """
    d = moo.run("down")
    print(f">>> 'down' (to fore corridor)\n{d}\n", flush=True)
    s = moo.run("south")
    print(f">>> 'south' (to aft corridor)\n{s}\n", flush=True)
    # The gate needs ARGUMENT-COUNTER > 4 — i.e. FIVE CONSECUTIVE `south`s.
    # Any non-south turn lets the i-argument abort daemon fire (it resets the
    # counter to 0 with "I knew you weren't serious..."), so send only `south`
    # and DON'T `look` until we're inside.  The escalation prompts ("Are you
    # sure?", "...Improbability Drive chamber...") mention the chamber too, so
    # break only on text unique to actually being in the room.
    inside_markers = ("nothing to see", "nothing happens", "houses the powerful", "few things")
    out = ""
    for _ in range(8):
        out = moo.run("south")
        print(f">>> 'south' (engine-room gate)\n{out}\n", flush=True)
        if any(m in out.lower() for m in inside_markers):
            break
    # Inside now: ENGINE-ROOM-F hides its contents until the third M-LOOK
    # (LOOK-COUNTER >= 3 reveals the spare drive and awards +25).  Entry was
    # LOOK-COUNTER 1, so `look` until the spare drive's FDESC appears.
    for _ in range(4):
        if "spare" in out.lower():
            break
        out = moo.run("look")
        print(f">>> 'look' (reveal spare drive)\n{out}\n", flush=True)
    take = moo.run("take spare drive")
    print(f">>> 'take spare drive'\n{take}\n", flush=True)
    return take


def _plug_drive(moo) -> str:
    """Carry the spare drive back to the Bridge and plug it into the receptacle.

    Engine Room ``north`` -> Aft Corridor, ``north`` -> Fore Corridor, ``up`` ->
    Bridge, then plug the large plug into the large receptacle (the manual
    override).  Sets DRIVE-TO-CONTROLS; Eddie warns about playing with a spare
    drive.  This is the deepest verified beat on the canonical win path — the
    improbability switch itself can't yet be activated (see hhg-shakedown
    BUGS.md: the ``turn on spare drive`` verb-atom mismatch).
    """
    moo.run("north")
    moo.run("north")
    moo.run("up")
    out = moo.run("plug large plug into large receptacle")
    print(f">>> 'plug large plug into large receptacle'\n{out}\n", flush=True)
    return out


_SENTINELS = {
    "__wait_for_ford__": _wait_for_ford,
    "__escape_earth__": _escape_earth,
    "__leave_dark__": _leave_dark,
    "__eat_peanuts__": _eat_peanuts,
    "__wait_for_satchel__": _wait_for_satchel,
    "__survive_vogons__": _survive_vogons,
    "__reach_heart_of_gold__": _reach_heart_of_gold,
    "__take_spare_drive__": _take_spare_drive,
    "__plug_drive__": _plug_drive,
}


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Run the HHG smoke test.")
    parser.add_argument(
        "--hostname",
        default="hhg.local",
        help="Site domain (also used as SSH host and ``phil+<host>`` user). Default: hhg.local.",
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
    _reset_hhg_state(hostname=hostname)

    # The SSH server listens on localhost:8022; the universe is selected by
    # the ``phil+<hostname>`` routing user, not by the SSH host (hhg.local
    # isn't a resolvable host).  Matches hhg_session.py's connection.
    with MooSSH(
        host="localhost",
        port=8022,
        user=f"phil+{hostname}",
        password="qw12er34",
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
        for cmd, expected in HHG_COMMANDS:
            t0 = time.monotonic()
            if cmd in _SENTINELS:
                out = _SENTINELS[cmd](moo)
                elapsed = time.monotonic() - t0
                timings.append((cmd, elapsed, False))
                print(f">>> {cmd!r} (sentinel, t={elapsed:.2f}s)\n", flush=True)
            else:
                out = moo.run(cmd)
                elapsed = time.monotonic() - t0
                timed_out = bool(getattr(moo, "last_run_timed_out", False))
                timings.append((cmd, elapsed, timed_out))
                tag = " [no-suffix]" if timed_out else ""
                print(f">>> {cmd!r} (out len={len(out)}, t={elapsed:.2f}s{tag})\n{out}\n", flush=True)
            if expected and expected.lower() not in out.lower():
                failures.append((cmd, expected, out))

        total_real = sum(t for _, t, to in timings if not to)
        print(f"\n=== TIMING ({len(timings)} steps, total real {total_real:.1f}s) ===")
        for cmd, t, _to in sorted(timings, key=lambda kv: kv[1], reverse=True)[:10]:
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
