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
from typing import Callable

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

    def connection_made(self, chan):
        self._chan = chan

    def setup_delimiters(self, prefix: str, suffix: str) -> None:
        """Switch to delimiter-extraction mode."""
        self._prefix = prefix
        self._suffix = suffix

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
            content_start = prefix_pos + len(self._prefix)
            content = self._buffer[content_start:suffix_pos]
            # Consume everything up to and including the suffix
            self._buffer = self._buffer[suffix_pos + len(self._suffix) :]

            cleaned = strip_ansi(content).strip()
            if cleaned:
                self._on_output(cleaned)


class MooConnection:
    """
    Manages the asyncssh connection lifecycle for a DjangoMOO agent session.

    After connect(), the session is in automation mode: PREFIX/SUFFIX delimiters
    are active, QUIET mode is on, and CPR is suppressed via TERM=moo-automation.
    """

    def __init__(self, ssh_config):
        self._config = ssh_config
        self._conn: asyncssh.SSHClientConnection | None = None
        self._chan = None
        self._session: MooSession | None = None

    async def connect(self, on_output: Callable[[str], None]) -> None:
        """Open the SSH connection and set up automation mode."""
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

        self._conn = await asyncssh.connect(**connect_kwargs)
        self._chan, self._session = await self._conn.create_session(
            lambda: MooSession(on_output),
            request_pty=True,
            term_type="moo-automation",
            encoding="utf-8",
        )
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
        self._session.setup_delimiters(prefix, suffix)

        self._chan.write(f"PREFIX {prefix}\n")
        self._chan.write(f"SUFFIX {suffix}\n")
        self._chan.write("QUIET enable\n")
        await asyncio.sleep(0.3)

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
