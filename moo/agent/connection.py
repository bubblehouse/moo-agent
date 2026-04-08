"""
SSH connection layer for moo-agent.

MooSession handles raw data from the asyncssh callback and extracts clean text
lines. MooConnection manages the connection lifecycle and automation setup.

Does not import from moo.core or trigger Django setup.
"""

import asyncio
import hashlib
import re
import time
from typing import Callable, cast

import asyncssh

# Strip all ANSI/VT100 escape sequences
ANSI_ESCAPE = re.compile(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def strip_ansi(text: str) -> str:
    return ANSI_ESCAPE.sub("", text).replace("\r", "")


class MooSession(asyncssh.SSHClientSession):
    """
    asyncssh session that buffers incoming data and extracts clean text.

    Before automation mode is active (no delimiters set), emits one on_output
    call per complete line. Once _prefix and _suffix are set by MooConnection,
    extracts only the content between those markers.
    """

    def __init__(self, on_output: Callable[[str], None]):
        self._on_output = on_output
        self._buffer = ""
        self._prefix: str | None = None
        self._suffix: str | None = None
        self._chan = None
        self._suppress: bool = False  # set True during automation setup to mute marker noise

    def connection_made(self, chan):
        self._chan = chan

    def setup_delimiters(self, prefix: str, suffix: str) -> None:
        """Switch to delimiter-extraction mode."""
        self._prefix = prefix
        self._suffix = suffix

    def set_suppress(self, suppress: bool) -> None:
        """Mute all output callbacks. Used during automation setup to swallow marker noise."""
        self._suppress = suppress
        if not suppress:
            # Discard any buffered content that accumulated during suppression.
            self._buffer = ""

    def data_received(self, data: str, datatype):
        self._buffer += data
        self._try_extract()

    def eof_received(self):
        pass

    def connection_lost(self, exc):
        pass

    def _try_extract(self):
        if self._prefix and self._suffix:
            self._extract_delimited()
        else:
            self._extract_lines()

    def _extract_lines(self):
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            if self._suppress:
                continue
            cleaned = strip_ansi(line).strip()
            if cleaned:
                self._on_output(cleaned)

    def _extract_delimited(self):
        while self._suffix in self._buffer:
            suffix_pos = self._buffer.index(self._suffix)
            # Find the most recent prefix before this suffix
            prefix_pos = self._buffer.rfind(self._prefix, 0, suffix_pos)
            if prefix_pos == -1:
                # No prefix found; discard up to and including the suffix
                self._buffer = self._buffer[suffix_pos + len(self._suffix) :]
                continue

            # Emit any preamble before the prefix as individual lines.
            # This captures print() output from a previous command that arrived
            # after that command's suffix (Celery flush order).
            preamble = self._buffer[:prefix_pos]
            if not self._suppress:
                for line in preamble.split("\n"):
                    cleaned = strip_ansi(line).strip()
                    if cleaned:
                        self._on_output(cleaned)

            content_start = prefix_pos + len(self._prefix)
            content = self._buffer[content_start:suffix_pos]
            # Consume everything up to and including the suffix
            self._buffer = self._buffer[suffix_pos + len(self._suffix) :]

            if not self._suppress:
                cleaned = strip_ansi(content).strip()
                if cleaned:
                    self._on_output(cleaned)

        if self._suppress:
            return

        # Eagerly flush any complete lines that sit in the buffer before the
        # next pending prefix. These are print() confirmations from commands
        # whose tell() output was empty — they would otherwise wait in the
        # buffer until the next command is sent, causing the agent to see no
        # confirmation and retry the same command repeatedly.
        next_prefix = self._buffer.find(self._prefix)
        flush_up_to = next_prefix if next_prefix != -1 else len(self._buffer)
        to_flush = self._buffer[:flush_up_to]
        if "\n" in to_flush:
            lines_text, remaining = to_flush.rsplit("\n", 1)
            for line in lines_text.split("\n"):
                cleaned = strip_ansi(line).strip()
                if cleaned:
                    self._on_output(cleaned)
            # Keep the incomplete trailing line + anything from the prefix onwards
            self._buffer = remaining + self._buffer[flush_up_to:]


class MooConnection:
    """
    Manages the asyncssh connection lifecycle for a DjangoMOO agent session.

    After connect(), the session is in automation mode: PREFIX/SUFFIX delimiters
    are active, QUIET mode is on, and CPR is suppressed via TERM=moo-automation.
    """

    def __init__(self, ssh_config) -> None:
        self._config = ssh_config
        self._conn: asyncssh.SSHClientConnection | None = None
        self._chan: asyncssh.SSHClientChannel | None = None
        self._session: MooSession | None = None
        self._on_output: Callable[[str], None] | None = None

    async def connect(self, on_output: Callable[[str], None]) -> None:
        """Open the SSH connection and set up automation mode."""
        self._on_output = on_output
        connect_kwargs = dict(
            host=self._config.host,
            port=self._config.port,
            username=self._config.user,
            known_hosts=None,
        )
        if self._config.key_file:
            connect_kwargs["client_keys"] = [self._config.key_file]
        elif self._config.password:
            connect_kwargs["password"] = self._config.password

        self._conn = await asyncssh.connect(
            **connect_kwargs,
            keepalive_interval=60,
            keepalive_count_max=5,
        )
        self._chan, session = await self._conn.create_session(
            lambda: MooSession(on_output),
            request_pty=True,
            term_type="moo-automation",
            encoding="utf-8",
        )
        self._session = cast(MooSession, session)
        await self._setup_automation_mode()

    async def _setup_automation_mode(self):
        """Enable PREFIX/SUFFIX delimiters and QUIET mode.

        The server fires confunc (which runs look_self) immediately on connect,
        before it processes any commands. That initial output has no delimiter
        markers, so we must let it arrive and drain in line-by-line mode first.
        Only after that initial burst settles do we send PREFIX/SUFFIX/QUIET and
        switch the session to delimiter mode.
        """
        # Let confunc output arrive and be emitted line-by-line.
        await asyncio.sleep(0.5)

        session_id = hashlib.sha256(str(time.time()).encode()).hexdigest()[:8]
        prefix = f">>MOO-START-{session_id}<<"
        suffix = f">>MOO-END-{session_id}<<"

        # Switch the session to delimiter mode, then send the commands.
        # OUTPUTPREFIX/OUTPUTSUFFIX wrap *all* output (tell() messages included),
        # not just the synchronous print() output that PREFIX/SUFFIX capture.
        # This ensures movement responses, arrive messages, and room descriptions
        # delivered via tell() are visible to the agent.
        #
        # Suppress output during setup: the confirmation messages from OUTPUTPREFIX,
        # OUTPUTSUFFIX, and QUIET contain the raw marker strings and produce noise
        # in the agent log. We discard everything until the session is fully ready.
        self._session.setup_delimiters(prefix, suffix)
        # Emit prefix/suffix values before suppression so they appear in the log.
        if self._on_output:
            self._on_output(f"Global output prefix set to: {prefix}")
            self._on_output(f"Global output suffix set to: {suffix}")
        self._session.set_suppress(True)

        self._chan.write(f"OUTPUTPREFIX {prefix}\n")
        self._chan.write(f"OUTPUTSUFFIX {suffix}\n")
        self._chan.write("QUIET enable\n")
        await asyncio.sleep(0.3)

        # Lift suppression — set_suppress(False) also clears the buffer so
        # setup artifacts do not resurface as preamble on the next command.
        self._session.set_suppress(False)

    def send(self, command: str) -> None:
        """Write a command to the MOO session."""
        if self._chan:
            self._chan.write(command + "\n")

    async def disconnect(self) -> None:
        """Send @quit and close the connection."""
        if self._chan:
            try:
                self._chan.write("@quit\n")
                await asyncio.sleep(0.2)
            except Exception:  # pylint: disable=broad-exception-caught
                pass
        if self._conn:
            self._conn.close()
            self._conn = None
