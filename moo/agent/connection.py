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
        # Stage 2 one-shot subscribers. ``MooConnection.request()`` installs
        # these to consume a bracketed slice (and optionally one late
        # async-pattern match) without re-emitting through ``on_output``,
        # avoiding double-exposure in the brain's rolling window.
        self._request_slice_future: asyncio.Future[str] | None = None
        self._request_async_match: tuple[re.Pattern[str], asyncio.Future[str]] | None = None

    @property
    def iac_capabilities(self) -> dict[str, object]:
        """Return a snapshot of the negotiated IAC capabilities."""
        return dict(self._iac_negotiator.capabilities)

    def install_slice_future(self, fut: "asyncio.Future[str]") -> None:
        """Subscribe a single bracketed slice to the given future.

        The next PREFIX/SUFFIX-bracketed chunk fulfils ``fut`` instead of
        emitting through ``on_output``. The subscription is one-shot; cleared
        on fulfilment, or by ``clear_request_subscriptions()`` on cancel.
        """
        self._request_slice_future = fut

    def install_async_match(self, pattern: re.Pattern[str], fut: "asyncio.Future[str]") -> None:
        """Subscribe the next line matching ``pattern`` to ``fut``.

        Used by ``MooConnection.request()`` to capture the late Celery ack
        line that arrives after the synchronous PREFIX/SUFFIX slice. One-shot.
        """
        self._request_async_match = (pattern, fut)

    def clear_request_subscriptions(self) -> None:
        """Clear any pending one-shot slice/async-match subscriptions.

        Called from ``MooConnection.request()``'s finally-block to guard
        against a future that was never fulfilled (cancelled task, timeout).
        """
        self._request_slice_future = None
        self._request_async_match = None

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
        if not cleaned:
            return
        # Async-match consumer: ``MooConnection.request(..., async_pattern=...)``
        # waits for a late Celery ack line. If the line matches, fulfill the
        # caller's future instead of emitting — the caller folds the line into
        # its own return value and post-processes for chain.py side effects.
        match_subscriber = self._request_async_match
        if match_subscriber is not None:
            pattern, fut = match_subscriber
            if not fut.done() and pattern.search(cleaned):
                fut.set_result(cleaned)
                self._request_async_match = None
                return
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
                # Stage 2 one-shot slice consumer: when ``MooConnection.request()``
                # installs a slice future, fulfill it with the bracketed content
                # rather than emitting through ``on_output``. The caller's tool
                # returns the slice to the model and runs chain.py side effects
                # explicitly, so suppressing emission here avoids re-appending
                # the same text into the brain's rolling window.
                if self._request_slice_future is not None and not self._request_slice_future.done():
                    cleaned = strip_ansi(content).strip()
                    self._request_slice_future.set_result(cleaned)
                    self._request_slice_future = None
                else:
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
        self._on_tool_response: Callable[[str], None] | None = None
        self._on_gmcp = on_gmcp
        self._on_mssp = on_mssp
        self._on_capability_change = on_capability_change
        # Serialises ``request()`` so concurrent tool dispatches don't
        # interleave PREFIX/SUFFIX brackets on the wire.
        self._request_lock = asyncio.Lock()

    def set_disconnect_callback(self, callback: Callable[[], None]) -> None:
        """Register a callback fired when the SSH connection is lost."""
        self._on_disconnect = callback

    def set_tool_response_callback(self, callback: Callable[[str], None]) -> None:
        """
        Register a side-channel callback fired with each bracketed slice that
        ``request()`` consumes. The model already sees the slice via the tool's
        return value, so the slice is NOT re-emitted through ``on_output``
        (that would double-expose in the brain's rolling window). The callback
        exists so the TUI/operator log + brain state-tracking
        (``_update_current_room_from``, etc.) still see the response.
        """
        self._on_tool_response = callback

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

    async def request(
        self,
        command: str,
        *,
        async_wait_s: float = 0.0,
        async_pattern: re.Pattern[str] | None = None,
    ) -> str:
        """
        Send a MOO command and return its PREFIX/SUFFIX-bracketed response.

        The Stage-2 building block. Each ``@agent.tool`` calls this once and
        returns the resulting string to the model. The bracketed slice is
        consumed via a one-shot future inside ``MooSession`` so it never
        re-emits through ``on_output`` — the model sees the response via the
        tool return, and the brain's rolling window does not double-expose
        the same text.

        For Celery-backed verbs (``@dig``, ``@create``, ``@edit verb``, etc.)
        the synchronous handler returns before the Celery task has emitted
        its ack line. Pass ``async_wait_s`` and ``async_pattern`` to wait up
        to that many additional seconds for a line matching the pattern; on
        match, the ack line is folded into the return value; on timeout, the
        return value carries the synchronous slice plus ``[async result
        pending]`` and the late line lands in the *next* tool call's
        post-PREFIX preamble.

        The connection's internal lock serialises concurrent calls, so a
        chain-handler auto-advance running in parallel with a tool's
        ``request()`` cannot interleave their brackets on the wire.
        """
        if self._session is None or self._chan is None:
            raise RuntimeError("MooConnection not connected — request() called before connect().")

        loop = asyncio.get_running_loop()
        async with self._request_lock:
            slice_fut: asyncio.Future[str] = loop.create_future()
            self._session.install_slice_future(slice_fut)

            self._chan.write(command + "\n")

            try:
                slice_text = await slice_fut
            finally:
                # Defensive clear in case the future was never fulfilled
                # (e.g. cancellation between write and await).
                self._session.clear_request_subscriptions()

            if async_pattern is None or async_wait_s <= 0:
                if self._on_tool_response is not None and slice_text:
                    self._on_tool_response(slice_text)
                return slice_text

            match_fut: asyncio.Future[str] = loop.create_future()
            self._session.install_async_match(async_pattern, match_fut)
            try:
                extra = await asyncio.wait_for(match_fut, timeout=async_wait_s)
                combined = f"{slice_text}\n{extra}"
                if self._on_tool_response is not None:
                    self._on_tool_response(combined)
                return combined
            except asyncio.TimeoutError:
                combined = f"{slice_text}\n[async result pending]"
                if self._on_tool_response is not None and slice_text:
                    self._on_tool_response(slice_text)
                return combined
            finally:
                self._session.clear_request_subscriptions()

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
