"""
Tests for moo/agent/connection.py.

No real SSH connection — tests MooSession in isolation by calling data_received
directly. Does not require DJANGO_SETTINGS_MODULE.
"""

from moo.agent.connection import MooSession, strip_ansi
from moo.agent.iac import (
    DO,
    DONT,
    IAC,
    OPT_GMCP,
    OPT_MSP,
    OPT_NAWS,
    OPT_TTYPE,
    SB,
    SE,
    WILL,
    encode_cmd,
    encode_gmcp,
    encode_sb,
)


class _FakeChannel:
    """Minimal stand-in for asyncssh.SSHClientChannel for IAC integration tests."""

    def __init__(self) -> None:
        self.written: list[str] = []
        self.encoding = "utf-8"
        self.errors = "strict"

    def set_encoding(self, encoding: str, errors: str = "strict") -> None:
        self.encoding = encoding
        self.errors = errors

    def write(self, data: str) -> None:
        self.written.append(data)

    @property
    def written_bytes(self) -> bytes:
        return b"".join(s.encode(self.encoding, errors=self.errors) for s in self.written)


def _make_session():
    received = []
    session = MooSession(on_output=received.append)
    return session, received


def test_pre_delimiter_emits_per_line():
    session, received = _make_session()
    session.data_received("hello\nworld\n", None)
    assert received == ["hello", "world"]


def test_pre_delimiter_buffers_partial_lines():
    session, received = _make_session()
    session.data_received("hel", None)
    assert not received
    session.data_received("lo\n", None)
    assert received == ["hello"]


def test_pre_delimiter_strips_ansi():
    session, received = _make_session()
    session.data_received("\x1b[32mgreen\x1b[0m\n", None)
    assert received == ["green"]


def test_pre_delimiter_skips_blank_lines():
    session, received = _make_session()
    session.data_received("line1\n\n  \nline2\n", None)
    assert received == ["line1", "line2"]


def test_delimiter_mode_extracts_content():
    session, received = _make_session()
    session.setup_delimiters(">>START<<", ">>END<<")
    session.data_received(">>START<<hello world>>END<<", None)
    assert received == ["hello world"]


def test_delimiter_mode_strips_ansi():
    session, received = _make_session()
    session.setup_delimiters(">>START<<", ">>END<<")
    session.data_received(">>START<<\x1b[32mgreen text\x1b[0m>>END<<", None)
    assert received == ["green text"]


def test_delimiter_mode_multi_chunk():
    session, received = _make_session()
    session.setup_delimiters(">>START<<", ">>END<<")
    session.data_received(">>START<<hello ", None)
    assert not received
    session.data_received("world>>END<<", None)
    assert received == ["hello world"]


def test_delimiter_mode_multiple_responses():
    session, received = _make_session()
    session.setup_delimiters(">>S<<", ">>E<<")
    session.data_received(">>S<<first>>E<<>>S<<second>>E<<", None)
    assert received == ["first", "second"]


def test_delimiter_mode_ignores_stale_prefix():
    session, received = _make_session()
    session.setup_delimiters(">>S<<", ">>E<<")
    # Orphan suffix with no prefix — should discard and move on
    session.data_received("junk>>E<<>>S<<good>>E<<", None)
    assert received == ["good"]


def test_strip_ansi_removes_codes():
    assert strip_ansi("\x1b[1;32mHello\x1b[0m") == "Hello"
    assert strip_ansi("no codes here") == "no codes here"
    assert strip_ansi("\x1b[?25l") == ""


def test_delimiter_mode_captures_multiple_tell_messages():
    # Simulates OUTPUTPREFIX/OUTPUTSUFFIX: tell() wraps each message individually.
    # This is the pattern produced by go north — leave msg, arrive msg, room
    # description — each wrapped in its own marker pair by process_messages().
    session, received = _make_session()
    session.setup_delimiters(">>S<<", ">>E<<")
    data = ">>S<<You leave The Laboratory.>>E<<>>S<<You arrive at The Workshop.>>E<<>>S<<The Workshop\nA room.>>E<<"
    session.data_received(data, None)
    assert received == ["You leave The Laboratory.", "You arrive at The Workshop.", "The Workshop\nA room."]


def test_delimiter_mode_emits_preamble_before_prefix():
    # print() output from command N arrives AFTER command N's suffix, as preamble
    # before command N+1's prefix. It must not be silently discarded.
    session, received = _make_session()
    session.setup_delimiters(">>S<<", ">>E<<")
    # Command N: empty window (no tell() output), followed by print() preamble
    session.data_received(">>S<<>>E<<Set property text on #23\n>>S<<next command output>>E<<", None)
    assert "Set property text on #23" in received
    assert "next command output" in received


def test_delimiter_mode_eagerly_flushes_complete_lines():
    # print() confirmations arrive after the suffix but before the next command
    # is sent. Without eager flushing they sit in the buffer until the next
    # prefix arrives, causing the agent to see no confirmation and retry.
    session, received = _make_session()
    session.setup_delimiters(">>S<<", ">>E<<")
    # First command window processed, then print() confirmation arrives alone
    session.data_received(">>S<<room description>>E<<", None)
    assert received == ["room description"]
    received.clear()
    # Confirmation arrives without a following prefix yet
    session.data_received("Set property text on #45 (pressure gauge)\n", None)
    assert received == ["Set property text on #45 (pressure gauge)"]


def test_delimiter_mode_drops_inline_prompt_before_prefix():
    """In raw mode the server emits its colored prompt (e.g. `>>> `) on the
    same wire line as the next OUTPUTPREFIX marker — there is no `\\n` between
    the prompt and the prefix. That prompt fragment is partial content and
    must NOT be emitted as a preamble line, even after ANSI is stripped."""
    session, received = _make_session()
    session.setup_delimiters(">>S<<", ">>E<<")
    # Simulate a raw-mode stream: previous command's complete suffix, then
    # ANSI-colored prompt + next prefix on the same line, then real content.
    session.data_received(">>S<<first response>>E<<\x1b[38;2;0;170;0m>>> \x1b[0m>>S<<second response>>E<<", None)
    assert "first response" in received
    assert "second response" in received
    assert ">>>" not in received  # the bare prompt fragment must be dropped


def test_delimiter_mode_does_not_emit_partial_line_eagerly():
    # A partial line (no trailing \n) must stay in the buffer — we can't know
    # whether it's complete until more data arrives.
    session, received = _make_session()
    session.setup_delimiters(">>S<<", ">>E<<")
    session.data_received(">>S<<output>>E<<", None)
    received.clear()
    session.data_received("incomplete", None)
    assert not received
    # The line is emitted once a newline arrives
    session.data_received(" line\n", None)
    assert received == ["incomplete line"]


def test_suppress_mutes_all_output():
    # During automation setup, set_suppress(True) prevents any output callbacks.
    # set_suppress(False) clears the buffer and resumes normal emission.
    session, received = _make_session()
    session.setup_delimiters(">>S<<", ">>E<<")
    session.set_suppress(True)
    # Simulate OUTPUTPREFIX/OUTPUTSUFFIX/a11y confirmations arriving during setup
    setup_noise = "Global output prefix set to: >>S<<\nGlobal output suffix set to: >>E<<\nquiet on\n"
    session.data_received(f"{setup_noise}>>S<<setup artifact>>E<<", None)
    assert not received
    # Resume — buffer is cleared, subsequent real output is emitted normally
    session.set_suppress(False)
    session.data_received(">>S<<first real output>>E<<", None)
    assert received == ["first real output"]


def test_strip_ansi_removes_carriage_returns():
    # PTY converts \n to \r\n; strip_ansi must remove the embedded \r so the
    # TUI doesn't display ^M characters.
    assert strip_ansi("line one\r\nline two\r\n") == "line one\nline two\n"
    assert strip_ansi("text\r") == "text"


def test_connection_lost_fires_disconnect_callback():
    # connection_lost() must call the on_disconnect callback so the reconnect
    # watcher in cli.py can detect dropped SSH connections.
    fired = []
    session = MooSession(on_output=lambda _: None, on_disconnect=lambda: fired.append(True))
    session.connection_lost(None)
    assert fired == [True]


def test_connection_lost_no_callback_is_safe():
    # connection_lost() with no on_disconnect registered must not raise.
    session = MooSession(on_output=lambda _: None)
    session.connection_lost(None)  # should not raise


# --- IAC handshake wiring ---------------------------------------------------


def _bytes_to_session_str(data: bytes) -> str:
    """Mimic what asyncssh hands to data_received when the channel is in
    surrogateescape mode: 0xFF bytes arrive as \\udcff surrogates."""
    return data.decode("utf-8", errors="surrogateescape")


def test_connection_made_sets_surrogateescape_encoding():
    chan = _FakeChannel()
    session = MooSession(on_output=lambda _: None)
    session.connection_made(chan)
    assert chan.encoding == "utf-8"
    assert chan.errors == "surrogateescape"


def test_strips_iac_handshake_bytes_from_buffer():
    """IAC bytes must not leak into the text buffer or _emit_line callbacks."""
    received: list[str] = []
    session = MooSession(on_output=received.append)
    chan = _FakeChannel()
    session.connection_made(chan)
    payload = b"You are in The Laboratory.\n" + encode_cmd(WILL, OPT_GMCP) + b"A bright room.\n"
    session.data_received(_bytes_to_session_str(payload), None)
    assert "You are in The Laboratory." in received
    assert "A bright room." in received
    assert not any("\udcff" in line for line in received)


def test_replies_to_will_gmcp_with_do_and_handshake():
    chan = _FakeChannel()
    session = MooSession(on_output=lambda _: None)
    session.connection_made(chan)
    session.data_received(_bytes_to_session_str(encode_cmd(WILL, OPT_GMCP)), None)
    written = chan.written_bytes
    assert encode_cmd(DO, OPT_GMCP) in written
    assert b"Core.Hello" in written
    assert b"Core.Supports.Set" in written


def test_refuses_will_msp():
    """Agent can't play sounds — must reply DONT MSP."""
    chan = _FakeChannel()
    session = MooSession(on_output=lambda _: None)
    session.connection_made(chan)
    session.data_received(_bytes_to_session_str(encode_cmd(WILL, OPT_MSP)), None)
    assert encode_cmd(DONT, OPT_MSP) in chan.written_bytes


def test_completes_ttype_handshake_in_three_stages():
    chan = _FakeChannel()
    session = MooSession(on_output=lambda _: None)
    session.connection_made(chan)
    session.data_received(_bytes_to_session_str(encode_cmd(DO, OPT_TTYPE)), None)
    send_frame = encode_sb(OPT_TTYPE, bytes((1,)))  # TTYPE_SEND = 1
    for _ in range(3):
        session.data_received(_bytes_to_session_str(send_frame), None)
    written = chan.written_bytes
    assert written.count(bytes((IAC, SB, OPT_TTYPE, 0))) == 3  # 0 = TTYPE_IS
    assert b"MTTS " in written
    assert b"moo-agent" in written


def test_dispatches_gmcp_to_callback():
    received_gmcp: list[tuple] = []
    session = MooSession(
        on_output=lambda _: None,
        on_gmcp=lambda mod, data: received_gmcp.append((mod, data)),
    )
    chan = _FakeChannel()
    session.connection_made(chan)
    session.data_received(_bytes_to_session_str(encode_gmcp("Room.Info", {"name": "Lab"})), None)
    assert received_gmcp == [("Room.Info", {"name": "Lab"})]


def test_iac_capabilities_property_starts_empty():
    session = MooSession(on_output=lambda _: None)
    caps = session.iac_capabilities
    assert caps.get("gmcp") is False
    assert caps.get("ttype") is False


def test_iac_capabilities_reflect_negotiation():
    chan = _FakeChannel()
    session = MooSession(on_output=lambda _: None)
    session.connection_made(chan)
    session.data_received(_bytes_to_session_str(encode_cmd(WILL, OPT_GMCP)), None)
    assert session.iac_capabilities["gmcp"] is True


def test_iac_payload_with_iac_iac_escape():
    """IAC IAC inside SB payload must be unescaped to literal 0xFF."""
    received_gmcp: list[tuple] = []
    session = MooSession(
        on_output=lambda _: None,
        on_gmcp=lambda mod, data: received_gmcp.append((mod, data)),
    )
    session.connection_made(_FakeChannel())
    weird_payload = b'Room.Info {"name":"x\xffy"}'
    frame = bytes((IAC, SB, OPT_GMCP)) + weird_payload.replace(bytes((IAC,)), bytes((IAC, IAC))) + bytes((IAC, SE))
    session.data_received(_bytes_to_session_str(frame), None)
    assert received_gmcp
    module, data = received_gmcp[0]
    assert module == "Room.Info"
    assert "name" in data
