"""
SSH connection layer for moo-agent. See
``docs/source/explanation/agent-internals.md`` (The Connection Layer, IAC)
for the design narrative.
"""

import asyncio
import hashlib
import logging
import re
import time
from typing import Callable, Optional, cast

import asyncssh

from .iac import AgentIacNegotiator, IacParser

log = logging.getLogger(__name__)

# Strip all ANSI/VT100 escape sequences
ANSI_ESCAPE = re.compile(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def _iac_bytes_to_str(data: bytes) -> str:
    """Convert raw IAC bytes to a str the surrogate-escape UTF-8 channel can re-emit verbatim."""
    return data.decode("utf-8", errors="surrogateescape")


def _str_to_iac_bytes(data: str) -> bytes:
    """Inverse of :func:`_iac_bytes_to_str` — used to feed inbound channel str data to the IAC parser."""
    return data.encode("utf-8", errors="surrogateescape")


def strip_ansi(text: str) -> str:
    return ANSI_ESCAPE.sub("", text).replace("\r", "")


class MooSession(asyncssh.SSHClientSession):
    """
    asyncssh session — IAC parsing, PREFIX/SUFFIX delimiter extraction.

    Emits one on_output call per complete line until ``setup_delimiters``
    is called, then switches to delimited extraction. See agent-internals:
    The Connection Layer.
    """

    def __init__(
        self,
        on_output: Callable[[str], None],
        on_disconnect: Callable[[], None] | None = None,
        *,
        on_gmcp: Optional[Callable[[str, object], None]] = None,
        on_mssp: Optional[Callable[[dict[str, list[str]]], None]] = None,
        on_capability_change: Optional[Callable[[dict[str, object]], None]] = None,
    ):
        self._on_output = on_output
        self._on_disconnect = on_disconnect
        self._buffer = ""
        self._prefix: str | None = None
        self._suffix: str | None = None
        self._chan = None
        self._suppress: bool = False  # set True during session setup to mute marker noise
        self._iac_parser = IacParser()
        self._iac_negotiator = AgentIacNegotiator(
            on_gmcp=on_gmcp,
            on_mssp=on_mssp,
            on_capability_change=on_capability_change,
        )

    @property
    def iac_capabilities(self) -> dict[str, object]:
        """Return a snapshot of the negotiated IAC capabilities."""
        return dict(self._iac_negotiator.capabilities)

    def connection_made(self, chan):
        self._chan = chan
        # surrogateescape lets 0xFF IAC bytes round-trip as \udcff surrogates.
        try:
            chan.set_encoding("utf-8", errors="surrogateescape")
        except Exception:  # pylint: disable=broad-except
            log.exception("failed to set surrogateescape encoding on channel")

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
        data = self._strip_iac(data)
        if not data:
            return
        self._buffer += data
        self._try_extract()

    def _strip_iac(self, data: str) -> str:
        """Feed inbound bytes through the IAC parser; reply on the channel; return non-IAC text."""
        try:
            data_bytes = _str_to_iac_bytes(data)
        except Exception:  # pylint: disable=broad-except
            log.exception("failed to encode inbound data for IAC parser")
            return data
        events, residual = self._iac_parser.feed(data_bytes)
        for event in events:
            try:
                reply = self._iac_negotiator.handle(event)
            except Exception:  # pylint: disable=broad-except
                log.exception("IAC negotiator failed on event %r", event)
                continue
            if reply and self._chan is not None:
                try:
                    self._chan.write(_iac_bytes_to_str(reply))
                except Exception:  # pylint: disable=broad-except
                    log.exception("failed to write IAC reply to channel")
        return _iac_bytes_to_str(residual)

    def eof_received(self):
        pass

    def connection_lost(self, exc):
        if self._on_disconnect:
            self._on_disconnect()

    def _try_extract(self):
        if self._prefix and self._suffix:
            self._extract_delimited()
        else:
            self._extract_lines()

    def _emit_line(self, line: str) -> None:
        cleaned = strip_ansi(line).strip()
        if cleaned:
            self._on_output(cleaned)

    def _extract_lines(self):
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            if self._suppress:
                continue
            self._emit_line(line)

    def _extract_delimited(self):
        while self._suffix in self._buffer:
            suffix_pos = self._buffer.index(self._suffix)
            # Find the most recent prefix before this suffix
            prefix_pos = self._buffer.rfind(self._prefix, 0, suffix_pos)
            if prefix_pos == -1:
                # No prefix found; discard up to and including the suffix
                self._buffer = self._buffer[suffix_pos + len(self._suffix) :]
                continue

            # Emit complete preamble lines from before this PREFIX (late
            # Celery print() output). See agent-internals: Preamble extraction.
            preamble = self._buffer[:prefix_pos]
            if not self._suppress and "\n" in preamble:
                complete, _trailing = preamble.rsplit("\n", 1)
                for line in complete.split("\n"):
                    self._emit_line(line)

            content_start = prefix_pos + len(self._prefix)
            content = self._buffer[content_start:suffix_pos]
            # Consume everything up to and including the suffix
            self._buffer = self._buffer[suffix_pos + len(self._suffix) :]

            if not self._suppress:
                self._emit_line(content)

        if self._suppress:
            return

        # Eagerly flush print() confirmations sitting ahead of the next
        # PREFIX. See agent-internals: Eager flush.
        next_prefix = self._buffer.find(self._prefix)
        flush_up_to = next_prefix if next_prefix != -1 else len(self._buffer)
        to_flush = self._buffer[:flush_up_to]
        if "\n" in to_flush:
            lines_text, remaining = to_flush.rsplit("\n", 1)
            for line in lines_text.split("\n"):
                self._emit_line(line)
            # Keep the incomplete trailing line + anything from the prefix onwards
            self._buffer = remaining + self._buffer[flush_up_to:]


class MooConnection:
    """
    asyncssh connection lifecycle. See agent-internals: The Connection
    Layer for the TERM/IAC/PREFIX-SUFFIX flow.
    """

    def __init__(
        self,
        ssh_config,
        *,
        on_gmcp: Optional[Callable[[str, object], None]] = None,
        on_mssp: Optional[Callable[[dict[str, list[str]]], None]] = None,
        on_capability_change: Optional[Callable[[dict[str, object]], None]] = None,
    ) -> None:
        self._config = ssh_config
        self._conn: asyncssh.SSHClientConnection | None = None
        self._chan: asyncssh.SSHClientChannel | None = None
        self._session: MooSession | None = None
        self._on_output: Callable[[str], None] | None = None
        self._on_disconnect: Callable[[], None] | None = None
        self._on_gmcp = on_gmcp
        self._on_mssp = on_mssp
        self._on_capability_change = on_capability_change

    def set_disconnect_callback(self, callback: Callable[[], None]) -> None:
        """Register a callback fired when the SSH connection is lost."""
        self._on_disconnect = callback

    async def connect(self, on_output: Callable[[str], None]) -> None:
        """Open the SSH connection and set up the session."""
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
            keepalive_interval=15,
            keepalive_count_max=3,
            connect_timeout=30,
        )
        self._chan, session = await self._conn.create_session(
            lambda: MooSession(
                on_output,
                self._on_disconnect,
                on_gmcp=self._on_gmcp,
                on_mssp=self._on_mssp,
                on_capability_change=self._on_capability_change,
            ),
            request_pty=True,
            term_type="xterm-256-basic",
            encoding="utf-8",
        )
        self._session = cast(MooSession, session)
        await self._setup_session()

    @property
    def iac_capabilities(self) -> dict[str, object]:
        """Snapshot of negotiated IAC capabilities; empty before connect()."""
        if self._session is None:
            return {}
        return self._session.iac_capabilities

    async def _setup_session(self):
        """
        Send OUTPUTPREFIX / OUTPUTSUFFIX / ``a11y quiet on`` and switch to
        delimiter mode. Setup commands run in line mode so unrelated pages
        landing during setup are not dropped — see agent-internals:
        Why no suppress window during setup.

        The 0.4 s spacing accounts for Kombu publish→consume latency: each
        session-setting event must reach the shell's _session_settings dict
        before the next command's response is wrapped.
        """
        # Let confunc output arrive in line-by-line mode.
        await asyncio.sleep(0.5)

        session_id = hashlib.sha256(str(time.time()).encode()).hexdigest()[:8]
        prefix = f">>MOO-START-{session_id}<<"
        suffix = f">>MOO-END-{session_id}<<"

        self._chan.write(f"OUTPUTPREFIX {prefix}\n")
        await asyncio.sleep(0.4)
        self._chan.write(f"OUTPUTSUFFIX {suffix}\n")
        await asyncio.sleep(0.4)
        self._chan.write("a11y quiet on\n")
        await asyncio.sleep(0.4)

        self._session.setup_delimiters(prefix, suffix)
        if self._on_output:
            self._on_output(f"Global output prefix set to: {prefix}")
            self._on_output(f"Global output suffix set to: {suffix}")

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
