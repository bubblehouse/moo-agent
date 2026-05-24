#!/usr/bin/env python3
"""
moo_ssh.py - SSH automation for DjangoMOO wizard sessions.

Connects to a MOO server via SSH, executes commands, and supports automating
the full-screen verb editor. Designed for use by the game-designer skill.

Usage (CLI):
    python moo_ssh.py commands.txt
    python moo_ssh.py --host localhost --port 8022 "look" "north"

Usage (library):
    from moo_ssh import MooSSH
    with MooSSH() as moo:
        print(moo.run("look"))
        moo.edit_verb("drink", "Duff beer", "print('cheers')\\nthis.delete()")

Requirements:
    pip install pexpect
"""

import argparse
import hashlib
import re
import sys
import time

import pexpect

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 8022
DEFAULT_USER = "phil"
DEFAULT_PASSWORD = "qw12er34"
DEFAULT_TIMEOUT = 6  # seconds to wait after each command (must exceed CPR timeout ~2-3s)
FLUSH_TIMEOUT = 2.0  # seconds to flush stale output before a command
CONNECT_TIMEOUT = 20  # seconds to wait for initial connection

# Strip ANSI/VT100 escape sequences from captured output
ANSI_ESCAPE = re.compile(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def strip_ansi(text):
    """Remove all ANSI escape sequences from a string."""
    return ANSI_ESCAPE.sub("", text)


class MooSSH:
    """
    Interactive SSH session for DjangoMOO wizard automation.

    The MOO shell is a prompt_toolkit application over asyncssh, so it always
    produces ANSI escape sequences. This class uses pexpect with a PTY and
    timeout-based output capture (rather than prompt matching) to handle the
    ANSI-heavy output reliably.

    Two interaction modes:
    - run(cmd): sends a single command, waits, returns stripped output
    - edit_verb(verb, obj, code): opens the full-screen editor, types multi-line
      Python code, and saves with Ctrl+S + Y
    """

    def __init__(
        self,
        host=DEFAULT_HOST,
        port=DEFAULT_PORT,
        user=DEFAULT_USER,
        password=DEFAULT_PASSWORD,
        timeout=DEFAULT_TIMEOUT,
        verbose=True,
        prefix_wait=2.0,
    ):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.timeout = timeout
        self.verbose = verbose
        # Once the command has been sent, wait at most ``prefix_wait``
        # seconds for the PREFIX marker before declaring "no synchronous
        # output" and bailing.  The shell omits PREFIX/SUFFIX wrapping
        # for empty-content tasks (``moo/shell/prompt.py`` line 922), so
        # without this short-circuit the poll loop sits idle for the full
        # ``timeout`` (10s in the smoke).  2.0s comfortably exceeds every
        # real-work command's server time (slowest is ~0.4s) while still
        # cutting ~24s off the smoke wall-clock for the three known
        # no-output commands (pray / light match / launch).
        self.prefix_wait = prefix_wait
        # Set after every ``run()`` call: True when the SUFFIX marker was
        # never observed within ``self.timeout`` seconds.  This happens
        # when the verb produces no synchronous content — the shell
        # intentionally omits PREFIX/SUFFIX wrapping for empty-content
        # tasks (see ``moo/shell/prompt.py`` line 922 comment) — so the
        # poll loop exits at the deadline rather than on a real signal.
        # Callers can check this flag to distinguish "command produced no
        # output" from "command actually took 10s".
        self.last_run_timed_out = False
        self.child = None
        self.prefix_marker = None
        self.suffix_marker = None

    def _log(self, msg):
        if self.verbose:
            print(msg, file=sys.stderr, flush=True)

    def connect(self):
        """Open SSH connection and wait for the MOO session to stabilize."""
        # TERM=xterm-256-basic puts the server in raw mode with IAC negotiation.
        # Raw mode uses a line-oriented shell loop that does not issue CPR
        # (cursor position) queries — eliminating the ~2-3s timeout per command
        # that prompt_toolkit otherwise incurs. The server-emitted IAC handshake
        # and per-prompt EOR bytes do appear in pexpect output as garbage, but
        # they don't disturb the PREFIX/SUFFIX delimiter regexes.
        ssh_cmd = (
            "/bin/sh -c 'TERM=xterm-256-basic ssh -tt "
            "-o StrictHostKeyChecking=no "
            "-o UserKnownHostsFile=/dev/null "
            f"-p {self.port} {self.user}@{self.host}'"
        )
        self._log(f"[moo_ssh] Connecting to {self.user}@{self.host}:{self.port}...")
        self.child = pexpect.spawn(
            ssh_cmd,
            timeout=CONNECT_TIMEOUT,
            encoding="utf-8",
            codec_errors="replace",
        )

        idx = self.child.expect(["[Pp]assword:", pexpect.EOF, pexpect.TIMEOUT])
        if idx != 0:
            raise ConnectionError("SSH did not present a password prompt")
        self.child.sendline(self.password)

        # Wait for the MOO banner and initial render to settle
        self.child.expect(pexpect.TIMEOUT, timeout=4)
        self._log("[moo_ssh] Connected.")
        return self

    def enable_delimiters(self):
        """
        Enable PREFIX/SUFFIX markers for machine-parseable output.

        Generates unique session-specific markers and configures the MOO
        session to emit them around command output. This allows the client
        to detect when output is complete without relying on timeouts.

        Call this once after connect() to optimize parsing speed.
        """
        # Generate unique markers for this session
        session_id = hashlib.sha256(str(time.time()).encode()).hexdigest()[:8]
        self.prefix_marker = f">>MOO-START-{session_id}<<"
        self.suffix_marker = f">>MOO-END-{session_id}<<"

        # Configure MOO session (using standard timeout parsing for these setup commands)
        self._log(f"[moo_ssh] Enabling delimiters: {self.prefix_marker} / {self.suffix_marker}")
        self.run(f"PREFIX {self.prefix_marker}")
        self.run(f"SUFFIX {self.suffix_marker}")

        # Flush any stale output — the SUFFIX echo contains the suffix marker string,
        # which would cause the next run() call to exit immediately on stale data.
        self.child.expect(pexpect.TIMEOUT, timeout=1)
        self._log("[moo_ssh] Delimiters enabled")

    def enable_automation_mode(self):
        """
        Enable all automation optimizations in one call.

        Sets up PREFIX/SUFFIX delimiters for fast output detection, and
        enables quiet mode to suppress ANSI color codes so captured output
        is plain text without needing post-processing.

        Call this once after connect() before issuing build commands.
        """
        self.enable_delimiters()
        self.run("a11y quiet on")

    def run(self, command):
        """
        Send a single MOO command and return stripped output.

        If delimiters are enabled (via enable_delimiters()), polls for the
        suffix marker and returns output between prefix and suffix. Otherwise,
        falls back to timeout-based polling to capture async responses.
        """
        command = command.strip()
        if not command or command.startswith("#"):
            return ""

        # Drain any async output buffered since the last command.  Ambient
        # room daemons emit tell()s between commands (e.g. the forest
        # songbird's "chirping of a song bird"); if that text is still in
        # the pipe it lands ahead of this command's PREFIX marker and
        # _extract_delimited_output latches onto the wrong window, shifting
        # every subsequent command's response by one (and producing the
        # mangled ">>> �" marker).  Discard it so each command's
        # PREFIX/SUFFIX pair is unambiguous.
        if hasattr(self, "suffix_marker") and self.suffix_marker:
            try:
                while self.child.read_nonblocking(size=8192, timeout=0.05):
                    pass
            except (pexpect.TIMEOUT, pexpect.EOF):
                pass

        self.child.sendline(command)

        # If delimiters are enabled, wait for suffix marker
        if hasattr(self, "suffix_marker") and self.suffix_marker:
            accumulated = []
            deadline = time.time() + self.timeout
            # Two-phase deadline: short window to see PREFIX, full window
            # for SUFFIX once PREFIX has been observed.  Empty-content
            # tasks emit neither marker, so once prefix_deadline elapses
            # without a PREFIX we know no synchronous output is coming.
            prefix_deadline = time.time() + self.prefix_wait
            prefix_seen = False
            suffix_seen = False

            while time.time() < deadline:
                try:
                    chunk = self.child.read_nonblocking(size=8192, timeout=0.1)
                    if chunk:
                        accumulated.append(chunk)
                        # Check if we've received the suffix
                        full_output = "".join(accumulated)
                        if not prefix_seen and self.prefix_marker in full_output:
                            prefix_seen = True
                        if self.suffix_marker in full_output:
                            suffix_seen = True
                            break
                except (pexpect.TIMEOUT, pexpect.EOF):
                    time.sleep(0.1)
                if not prefix_seen and time.time() >= prefix_deadline:
                    # PREFIX never arrived — verb produced no synchronous
                    # output.  Bail rather than waiting for the full
                    # timeout (saves ~8s per such command).
                    break

            self.last_run_timed_out = not suffix_seen
            raw = "".join(accumulated)
            output = self._extract_delimited_output(raw)
            time.sleep(0.1)
        else:
            # Fallback path: no SUFFIX marker is configured, so "timeout"
            # isn't a meaningful concept — we always wait the fixed
            # window.  Keep the flag False for callers that check it.
            self.last_run_timed_out = False
            # Fallback: timeout-based polling (original behavior)
            accumulated = []
            for i in range(4):
                time.sleep(1.5 if i < 3 else 3.0)  # Longer final wait for late responses
                try:
                    # Read whatever is available right now (non-blocking with timeout=0)
                    chunk = self.child.read_nonblocking(size=8192, timeout=0)
                    if chunk:
                        accumulated.append(chunk)
                except (pexpect.TIMEOUT, pexpect.EOF):
                    pass

            raw = "".join(accumulated)
            output = strip_ansi(raw).strip()
            lines = [l for l in output.splitlines() if l.strip()]

            # The first non-empty line is usually the echoed command — drop it
            if lines and command[:20] in lines[0]:
                lines = lines[1:]

            output = "\n".join(lines).strip()

        self._log(f"  > {command[:120]}")
        if output:
            indented = output[:300].replace("\n", "\n    ")
            self._log(f"    {indented}")
        return output

    def run_raw(self, command):
        """
        Send a single MOO command and return the un-stripped accumulated buffer.

        Mirrors ``run()`` but skips the strip_ansi pass so callers can inspect
        OSC sequences (e.g. OSC 133 prompt/output markers) byte-for-byte.
        Useful for accessibility/screen-reader integration tests.
        """
        command = command.strip()
        if not command or command.startswith("#"):
            return ""

        self.child.sendline(command)
        accumulated = []
        deadline = time.time() + self.timeout
        suffix_seen_at = None
        # After the suffix marker arrives, drain for another 250ms so trailing
        # OSC sequences (e.g. OSC 133;D) that the server emits AFTER the
        # delimiter still land in the buffer.
        post_suffix_drain = 0.25
        while time.time() < deadline:
            try:
                chunk = self.child.read_nonblocking(size=8192, timeout=0.1)
                if chunk:
                    accumulated.append(chunk)
                    if self.suffix_marker and suffix_seen_at is None and self.suffix_marker in "".join(accumulated):
                        suffix_seen_at = time.time()
            except (pexpect.TIMEOUT, pexpect.EOF):
                time.sleep(0.05)
            if suffix_seen_at is not None and (time.time() - suffix_seen_at) >= post_suffix_drain:
                break
        return "".join(accumulated)

    def _extract_delimited_output(self, raw):
        """Extract output between PREFIX and SUFFIX markers."""
        stripped = strip_ansi(raw)

        # Find the markers
        start_idx = stripped.find(self.prefix_marker)
        end_idx = stripped.find(self.suffix_marker)

        if start_idx == -1 or end_idx == -1:
            # Markers not found, fall back to returning everything stripped
            self._log("[moo_ssh] WARNING: Delimiters not found in output")
            return stripped.strip()

        # Extract content between markers
        content = stripped[start_idx + len(self.prefix_marker) : end_idx]

        # Clean up: remove echoed command if present
        lines = [l for l in content.splitlines() if l.strip()]
        # First line might be the echoed command
        if lines:
            # Check if first line looks like a command echo
            first = lines[0].strip()
            # Remove if it matches the start of recent commands or looks like echo
            if any(
                first.startswith(cmd) for cmd in ["PREFIX", "SUFFIX", "a11y", "@accessibility", "look", "@", "help"]
            ):
                lines = lines[1:]

        return "\n".join(lines).strip()

    def edit_verb(self, verb_name, obj_name, code, clear_existing=False):
        """
        Create or update a verb using the full-screen editor.

        Opens the editor with `@edit verb <verb_name> on "<obj_name>"`, types
        the given Python code, and saves with Ctrl+S followed by Y.

        Args:
            verb_name: name of the verb (e.g., "drink")
            obj_name: name of the object (e.g., "Duff beer")
            code: Python source code as a string (actual newlines, not \\n)
            clear_existing: if True, attempt to select-all and delete before
                typing (use when updating a verb that already has code)
        """
        cmd = f'@edit verb {verb_name} on "{obj_name}"'
        lines = code.splitlines()
        self._log(f"  > {cmd}  [editor, {len(lines)} line(s)]")
        self.child.sendline(cmd)

        # Wait for the full-screen editor to render
        time.sleep(1.5)

        if clear_existing:
            # Ctrl+Home to go to start, then select to end and delete
            # prompt_toolkit emacs mode: no standard "select all" shortcut,
            # so we use escape-< (beginning of buffer) and escape-> (end).
            # Safest: send many Ctrl+K (kill line) sequences to clear
            for _ in range(50):
                self.child.send("\x0b")  # Ctrl+K: kill to end of line
                self.child.send("\x0e")  # Ctrl+N: next line (to move down)
            time.sleep(0.3)

        # Type the code line by line; PTY converts \r to \n for the application
        for i, line in enumerate(lines):
            self.child.send(line)
            if i < len(lines) - 1:
                self.child.send("\r")  # newline
            time.sleep(0.05)  # brief pause per line

        time.sleep(0.3)

        # Ctrl+S to request save, then Y to confirm
        self.child.send("\x13")
        time.sleep(0.5)
        self.child.send("y")

        # Wait for editor to close and MOO prompt to reappear
        time.sleep(2.0)

        self.child.expect(pexpect.TIMEOUT, timeout=1)
        output = strip_ansi(self.child.before or "").strip()
        self._log(f"    {output[:100]}" if output else "    (saved)")
        return output

    def run_many(self, commands):
        """
        Execute a sequence of commands.

        Each item can be:
        - str: a regular MOO command (passed to run())
        - dict with keys 'verb', 'obj', 'code': passed to edit_verb()
          Optional key 'clear' (bool) maps to clear_existing

        Returns a list of (command_str, output) tuples.
        """
        results = []
        for item in commands:
            if isinstance(item, dict):
                verb = item["verb"]
                obj = item["obj"]
                code = item["code"]
                clear = item.get("clear", False)
                output = self.edit_verb(verb, obj, code, clear_existing=clear)
                results.append((f'@edit verb {verb} on "{obj}"', output))
            else:
                cmd = item.strip()
                if not cmd or cmd.startswith("#"):
                    continue
                output = self.run(cmd)
                results.append((cmd, output))
        return results

    def disconnect(self):
        """Send @quit and close the SSH session."""
        if self.child and self.child.isalive():
            try:
                self.child.sendline("@quit")
                self.child.expect([pexpect.EOF, pexpect.TIMEOUT], timeout=5)
            except (pexpect.ExceptionPexpect, OSError):
                # Ignore errors during disconnect cleanup
                pass
            self.child.close()
        self.child = None
        self._log("[moo_ssh] Disconnected.")

    def __enter__(self):
        return self.connect()

    def __exit__(self, *args):
        self.disconnect()


def main():
    parser = argparse.ArgumentParser(description="Execute commands on a DjangoMOO server via SSH")
    parser.add_argument("--host", default=DEFAULT_HOST, help="SSH host (default: localhost)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="SSH port (default: 8022)")
    parser.add_argument("--user", default=DEFAULT_USER, help="SSH username (default: phil)")
    parser.add_argument("--password", default=DEFAULT_PASSWORD, help="SSH password")
    parser.add_argument(
        "--timeout", type=float, default=DEFAULT_TIMEOUT, help="Seconds to wait after each command (default: 3)"
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress status messages")
    parser.add_argument("commands", nargs="*", help="Commands to run, or a path to a text file (one command per line)")
    args = parser.parse_args()

    commands = []
    for arg in args.commands:
        # Treat as a file path if it looks like one and exists
        try:
            with open(arg, encoding="utf-8") as f:
                commands.extend(line.rstrip("\n") for line in f)
        except (FileNotFoundError, IsADirectoryError, PermissionError):
            commands.append(arg)

    if not commands:
        parser.print_help()
        sys.exit(1)

    moo = MooSSH(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        timeout=args.timeout,
        verbose=not args.quiet,
    )
    with moo:
        results = moo.run_many(commands)

    print(f"\n[moo_ssh] {len(results)} command(s) executed.", file=sys.stderr)


if __name__ == "__main__":
    main()
