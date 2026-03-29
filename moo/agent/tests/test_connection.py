"""
Tests for moo/agent/connection.py.

No real SSH connection — tests MooSession in isolation by calling data_received
directly. Does not require DJANGO_SETTINGS_MODULE.
"""

from moo.agent.connection import MooSession, strip_ansi


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


def test_suppress_mutes_all_output():
    # During automation setup, set_suppress(True) prevents any output callbacks.
    # set_suppress(False) clears the buffer and resumes normal emission.
    session, received = _make_session()
    session.setup_delimiters(">>S<<", ">>E<<")
    session.set_suppress(True)
    # Simulate OUTPUTPREFIX/OUTPUTSUFFIX/QUIET confirmations arriving during setup
    setup_noise = "Global output prefix set to: >>S<<\nGlobal output suffix set to: >>E<<\nQuiet mode enabled\n"
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
