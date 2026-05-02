"""Tests for moo.agent.iac — the client-side telnet IAC parser and negotiator."""

from __future__ import annotations

import json

import pytest

from moo.agent.iac import (
    AgentIacNegotiator,
    CHARSET_ACCEPTED,
    CHARSET_REJECTED,
    CHARSET_REQUEST,
    DEFAULT_MTTS,
    DO,
    DONT,
    EOR,
    GA,
    IAC,
    IacParser,
    MSSP_VAL,
    MSSP_VAR,
    OPT_CHARSET,
    OPT_EOR_OPT,
    OPT_GMCP,
    OPT_MSP,
    OPT_MSSP,
    OPT_NAWS,
    OPT_SGA,
    OPT_TTYPE,
    SB,
    SE,
    TTYPE_IS,
    TTYPE_SEND,
    WILL,
    WONT,
    encode_cmd,
    encode_gmcp,
    encode_naws,
    encode_sb,
    encode_ttype_is,
    parse_gmcp,
    parse_mssp,
    parse_ttype_subneg,
)


# --- Parser ----------------------------------------------------------------


class TestIacParser:
    def test_residual_passes_through(self):
        parser = IacParser()
        events, residual = parser.feed(b"hello world")
        assert not events
        assert residual == b"hello world"

    def test_simple_will_command(self):
        parser = IacParser()
        events, residual = parser.feed(bytes((IAC, WILL, OPT_GMCP)))
        assert events == [("cmd", WILL, OPT_GMCP)]
        assert residual == b""

    def test_iac_iac_escape(self):
        """IAC IAC inside the data stream is a literal 0xFF byte."""
        parser = IacParser()
        events, residual = parser.feed(b"a" + bytes((IAC, IAC)) + b"b")
        assert not events
        assert residual == bytes((ord("a"), 0xFF, ord("b")))

    def test_iac_iac_inside_subnegotiation(self):
        """IAC IAC inside SB payload is a literal 0xFF byte in the payload."""
        parser = IacParser()
        frame = bytes((IAC, SB, OPT_GMCP)) + b"x" + bytes((IAC, IAC)) + b"y" + bytes((IAC, SE))
        events, residual = parser.feed(frame)
        assert events == [("sb", OPT_GMCP, b"x\xffy")]
        assert residual == b""

    def test_subnegotiation_with_text_around(self):
        parser = IacParser()
        frame = b"before" + bytes((IAC, SB, OPT_GMCP)) + b"Core.Hello" + bytes((IAC, SE)) + b"after"
        events, residual = parser.feed(frame)
        assert events == [("sb", OPT_GMCP, b"Core.Hello")]
        assert residual == b"beforeafter"

    def test_partial_frame_across_feed_calls(self):
        parser = IacParser()
        # First chunk ends in the middle of a SB frame.
        e1, r1 = parser.feed(b"hi" + bytes((IAC, SB, OPT_GMCP)) + b"Core.")
        # Second chunk completes it.
        e2, r2 = parser.feed(b"Hello" + bytes((IAC, SE)) + b"bye")
        assert not e1
        assert r1 == b"hi"
        assert e2 == [("sb", OPT_GMCP, b"Core.Hello")]
        assert r2 == b"bye"

    def test_partial_iac_command_across_feed_calls(self):
        parser = IacParser()
        e1, r1 = parser.feed(bytes((IAC,)))
        e2, r2 = parser.feed(bytes((WILL, OPT_GMCP)))
        assert not e1
        assert r1 == b""
        assert e2 == [("cmd", WILL, OPT_GMCP)]
        assert r2 == b""

    def test_ga_event(self):
        parser = IacParser()
        events, residual = parser.feed(bytes((IAC, GA)))
        assert events == [("ga",)]
        assert residual == b""

    def test_eor_event(self):
        parser = IacParser()
        events, residual = parser.feed(bytes((IAC, EOR)))
        assert events == [("eor",)]
        assert residual == b""

    def test_unknown_iac_byte_is_dropped(self):
        parser = IacParser()
        events, residual = parser.feed(bytes((IAC, 0x42, ord("x"))))
        assert not events
        # The 0x42 was unknown, so it was consumed; "x" passed through.
        assert residual == b"x"


# --- Encoders ---------------------------------------------------------------


class TestEncoders:
    def test_encode_cmd(self):
        assert encode_cmd(WILL, OPT_TTYPE) == bytes((IAC, WILL, OPT_TTYPE))

    def test_encode_sb_simple(self):
        assert encode_sb(OPT_GMCP, b"hi") == bytes((IAC, SB, OPT_GMCP)) + b"hi" + bytes((IAC, SE))

    def test_encode_sb_doubles_iac(self):
        """A literal 0xFF in the payload must be doubled to escape it."""
        out = encode_sb(OPT_GMCP, bytes((0xFF,)))
        assert out == bytes((IAC, SB, OPT_GMCP, IAC, IAC, IAC, SE))

    def test_encode_ttype_is(self):
        out = encode_ttype_is("moo-agent")
        assert out == bytes((IAC, SB, OPT_TTYPE, TTYPE_IS)) + b"moo-agent" + bytes((IAC, SE))

    def test_encode_naws(self):
        out = encode_naws(80, 24)
        assert out == bytes((IAC, SB, OPT_NAWS, 0, 80, 0, 24, IAC, SE))

    def test_encode_naws_large_dimensions(self):
        out = encode_naws(1024, 768)
        assert out == bytes((IAC, SB, OPT_NAWS, 0x04, 0x00, 0x03, 0x00, IAC, SE))


# --- GMCP -------------------------------------------------------------------


class TestGmcp:
    def test_encode_with_data(self):
        out = encode_gmcp("Char.Vitals", {"hp": 50, "max": 100})
        # SB GMCP "Char.Vitals " + json + IAC SE
        assert out.startswith(bytes((IAC, SB, OPT_GMCP)) + b"Char.Vitals ")
        assert out.endswith(bytes((IAC, SE)))

    def test_encode_without_data(self):
        out = encode_gmcp("Core.Ping", None)
        assert out == bytes((IAC, SB, OPT_GMCP)) + b"Core.Ping" + bytes((IAC, SE))

    def test_round_trip(self):
        encoded = encode_gmcp("Char.Vitals", {"hp": 50, "max": 100})
        # Strip framing to get the raw payload.
        payload = encoded[3:-2]
        module, data = parse_gmcp(payload)
        assert module == "Char.Vitals"
        assert data == {"hp": 50, "max": 100}

    def test_parse_no_data(self):
        module, data = parse_gmcp(b"Core.Ping")
        assert module == "Core.Ping"
        assert data is None

    def test_parse_invalid_json_raises(self):
        with pytest.raises(json.JSONDecodeError):
            parse_gmcp(b"Char.Vitals not-json")


# --- TTYPE / MSSP parsers ---------------------------------------------------


class TestTtypeAndMssp:
    def test_parse_ttype_send(self):
        subcmd, value = parse_ttype_subneg(bytes((TTYPE_SEND,)))
        assert subcmd == TTYPE_SEND
        assert value == ""

    def test_parse_ttype_is_with_value(self):
        subcmd, value = parse_ttype_subneg(bytes((TTYPE_IS,)) + b"Mudlet")
        assert subcmd == TTYPE_IS
        assert value == "Mudlet"

    def test_parse_ttype_empty_payload_raises(self):
        with pytest.raises(ValueError):
            parse_ttype_subneg(b"")

    def test_parse_mssp_single_var(self):
        payload = bytes((MSSP_VAR,)) + b"NAME" + bytes((MSSP_VAL,)) + b"DjangoMOO"
        result = parse_mssp(payload)
        assert result == {"NAME": ["DjangoMOO"]}

    def test_parse_mssp_multiple_vars(self):
        payload = (
            bytes((MSSP_VAR,))
            + b"NAME"
            + bytes((MSSP_VAL,))
            + b"DjangoMOO"
            + bytes((MSSP_VAR,))
            + b"PLAYERS"
            + bytes((MSSP_VAL,))
            + b"4"
        )
        result = parse_mssp(payload)
        assert result == {"NAME": ["DjangoMOO"], "PLAYERS": ["4"]}

    def test_parse_mssp_multi_value(self):
        payload = bytes((MSSP_VAR,)) + b"GENRE" + bytes((MSSP_VAL,)) + b"Custom" + bytes((MSSP_VAL,)) + b"Roleplay"
        result = parse_mssp(payload)
        assert result == {"GENRE": ["Custom", "Roleplay"]}


# --- Negotiator -------------------------------------------------------------


class TestNegotiator:
    def test_will_gmcp_returns_do_plus_handshake(self):
        gmcp_calls: list[tuple] = []
        neg = AgentIacNegotiator(on_gmcp=lambda mod, data: gmcp_calls.append((mod, data)))
        reply = neg.handle(("cmd", WILL, OPT_GMCP))
        # Must start with DO GMCP, then the Hello + Supports.Set GMCP frames.
        assert reply.startswith(encode_cmd(DO, OPT_GMCP))
        rest = reply[len(encode_cmd(DO, OPT_GMCP)) :]
        # Run the rest back through a parser to extract the GMCP frames the
        # negotiator queued up.
        parser = IacParser()
        events, _ = parser.feed(rest)
        gmcp_modules = [parse_gmcp(payload)[0] for kind, opt, payload in events if kind == "sb" and opt == OPT_GMCP]
        assert "Core.Hello" in gmcp_modules
        assert "Core.Supports.Set" in gmcp_modules
        # Hello payload includes our client name.
        hello_payload = next(
            payload
            for kind, opt, payload in events
            if kind == "sb" and opt == OPT_GMCP and parse_gmcp(payload)[0] == "Core.Hello"
        )
        _, hello_data = parse_gmcp(hello_payload)
        assert hello_data["client"] == "moo-agent"
        # Supports.Set advertises Char/Room/Comm/MSSP and NOT Editor.
        supports_payload = next(
            payload
            for kind, opt, payload in events
            if kind == "sb" and opt == OPT_GMCP and parse_gmcp(payload)[0] == "Core.Supports.Set"
        )
        _, supports_data = parse_gmcp(supports_payload)
        assert "Editor 1" not in supports_data
        assert any(s.startswith("Char") for s in supports_data)
        assert any(s.startswith("Room") for s in supports_data)
        assert neg.capabilities["gmcp"] is True

    def test_will_msp_is_refused(self):
        """We can't play sounds — refuse MSP."""
        neg = AgentIacNegotiator()
        reply = neg.handle(("cmd", WILL, OPT_MSP))
        assert reply == encode_cmd(DONT, OPT_MSP)

    def test_will_eor_is_accepted(self):
        neg = AgentIacNegotiator()
        reply = neg.handle(("cmd", WILL, OPT_EOR_OPT))
        assert reply == encode_cmd(DO, OPT_EOR_OPT)
        assert neg.capabilities["eor"] is True

    def test_will_mssp_is_accepted(self):
        neg = AgentIacNegotiator()
        reply = neg.handle(("cmd", WILL, OPT_MSSP))
        assert reply == encode_cmd(DO, OPT_MSSP)
        assert neg.capabilities["mssp"] is True

    def test_wont_sga_is_silent_when_never_enabled(self):
        """Server's WONT SGA arrives at startup. Per RFC 1143 we don't reply
        when our state already matches (NO, NO) — replying would invite a
        DONT SGA back and create a negotiation loop on some servers."""
        neg = AgentIacNegotiator()
        reply = neg.handle(("cmd", WONT, OPT_SGA))
        assert reply == b""

    def test_do_ttype_arms_handshake(self):
        neg = AgentIacNegotiator()
        reply = neg.handle(("cmd", DO, OPT_TTYPE))
        assert reply == encode_cmd(WILL, OPT_TTYPE)
        # ttype_stage is now armed for the SEND that should follow.
        assert neg._ttype_stage == 1  # pylint: disable=protected-access

    def test_do_naws_replies_with_window_size(self):
        neg = AgentIacNegotiator(naws=(120, 40))
        reply = neg.handle(("cmd", DO, OPT_NAWS))
        # Reply is WILL NAWS followed immediately by the window-size SB frame.
        assert reply.startswith(encode_cmd(WILL, OPT_NAWS))
        rest = reply[len(encode_cmd(WILL, OPT_NAWS)) :]
        assert rest == encode_naws(120, 40)
        assert neg.capabilities["naws"] is True

    def test_ttype_three_stage_handshake(self):
        neg = AgentIacNegotiator(client_name="moo-agent", terminal="XTERM-256COLOR", mtts=DEFAULT_MTTS)
        # Server: DO TTYPE
        neg.handle(("cmd", DO, OPT_TTYPE))
        # Server: SB TTYPE SEND (stage 1 → IS moo-agent)
        reply = neg.handle(("sb", OPT_TTYPE, bytes((TTYPE_SEND,))))
        assert reply == encode_ttype_is("moo-agent")
        # Server: SB TTYPE SEND again (stage 2 → IS XTERM-256COLOR)
        reply = neg.handle(("sb", OPT_TTYPE, bytes((TTYPE_SEND,))))
        assert reply == encode_ttype_is("XTERM-256COLOR")
        # Server: SB TTYPE SEND a third time (stage 3 → IS MTTS <bitfield>)
        reply = neg.handle(("sb", OPT_TTYPE, bytes((TTYPE_SEND,))))
        assert reply == encode_ttype_is(f"MTTS {DEFAULT_MTTS}")
        assert neg.capabilities["ttype"] is True

    def test_ttype_loops_on_extra_send_after_stage_3(self):
        """If the server keeps asking after MTTS, return the terminal value (loop signal)."""
        neg = AgentIacNegotiator(terminal="XTERM-256COLOR")
        neg.handle(("cmd", DO, OPT_TTYPE))
        for _ in range(3):
            neg.handle(("sb", OPT_TTYPE, bytes((TTYPE_SEND,))))
        # Stage 4: loop on terminal.
        reply = neg.handle(("sb", OPT_TTYPE, bytes((TTYPE_SEND,))))
        assert reply == encode_ttype_is("XTERM-256COLOR")

    def test_gmcp_inbound_is_dispatched_to_callback(self):
        captured: list[tuple] = []
        neg = AgentIacNegotiator(on_gmcp=lambda mod, data: captured.append((mod, data)))
        # Server's already-enabled GMCP sends Room.Info.
        room_info = encode_gmcp("Room.Info", {"name": "Lab", "exits": ["north"]})
        # Strip framing to mimic what the parser hands the negotiator.
        sb_payload = room_info[3:-2]
        neg.handle(("sb", OPT_GMCP, sb_payload))
        assert captured == [("Room.Info", {"name": "Lab", "exits": ["north"]})]

    def test_gmcp_callback_exception_is_swallowed(self):
        def boom(_mod, _data):
            raise RuntimeError("oops")

        neg = AgentIacNegotiator(on_gmcp=boom)
        # Should not raise.
        neg.handle(("sb", OPT_GMCP, b"Char.Vitals"))

    def test_mssp_inbound_is_dispatched_to_callback(self):
        captured: list[dict] = []
        neg = AgentIacNegotiator(on_mssp=captured.append)
        payload = bytes((MSSP_VAR,)) + b"NAME" + bytes((MSSP_VAL,)) + b"DjangoMOO"
        neg.handle(("sb", OPT_MSSP, payload))
        assert captured == [{"NAME": ["DjangoMOO"]}]

    def test_charset_request_utf8_accepted(self):
        neg = AgentIacNegotiator()
        # SB CHARSET REQUEST <sep=" "> "UTF-8"
        payload = bytes((CHARSET_REQUEST,)) + b" UTF-8"
        reply = neg.handle(("sb", OPT_CHARSET, payload))
        assert reply == encode_sb(OPT_CHARSET, bytes((CHARSET_ACCEPTED,)) + b"UTF-8")

    def test_charset_request_unknown_rejected(self):
        neg = AgentIacNegotiator()
        payload = bytes((CHARSET_REQUEST,)) + b" LATIN-1"
        reply = neg.handle(("sb", OPT_CHARSET, payload))
        assert reply == encode_sb(OPT_CHARSET, bytes((CHARSET_REJECTED,)))

    def test_capability_change_callback_fires(self):
        events: list[dict] = []
        neg = AgentIacNegotiator(on_capability_change=events.append)
        neg.handle(("cmd", WILL, OPT_GMCP))
        assert events
        assert events[-1]["gmcp"] is True

    def test_full_server_initial_offer_sequence(self):
        """End-to-end: feed the server's initial offer through parser+negotiator,
        verify the agent replies with a sensible handshake."""
        neg = AgentIacNegotiator()
        parser = IacParser()
        # Recreate what the django-moo server sends in initial_offers().
        server_offer = b"".join(
            [
                encode_cmd(WILL, OPT_GMCP),
                encode_cmd(WILL, OPT_MSSP),
                encode_cmd(WILL, OPT_MSP),
                encode_cmd(WILL, OPT_EOR_OPT),
                encode_cmd(WILL, OPT_CHARSET),
                encode_cmd(WONT, OPT_SGA),
                encode_cmd(DO, OPT_TTYPE),
                encode_cmd(DO, OPT_NAWS),
            ]
        )
        events, residual = parser.feed(server_offer)
        assert residual == b""
        replies = b""
        for event in events:
            replies += neg.handle(event)
        # Replies should accept GMCP/MSSP/EOR/CHARSET, refuse MSP, ack SGA,
        # offer TTYPE/NAWS, and include the GMCP handshake + NAWS dimensions.
        reply_parser = IacParser()
        reply_events, _ = reply_parser.feed(replies)
        cmd_pairs = [(c, o) for kind, c, o in reply_events if kind == "cmd"]
        assert (DO, OPT_GMCP) in cmd_pairs
        assert (DO, OPT_MSSP) in cmd_pairs
        assert (DONT, OPT_MSP) in cmd_pairs
        assert (DO, OPT_EOR_OPT) in cmd_pairs
        assert (DO, OPT_CHARSET) in cmd_pairs
        # WONT SGA gets no reply per RFC 1143 (state was already NO, suppress
        # to avoid a negotiation loop with servers that echo DONT back).
        assert (DONT, OPT_SGA) not in cmd_pairs
        assert (WILL, OPT_TTYPE) in cmd_pairs
        assert (WILL, OPT_NAWS) in cmd_pairs
        # And we sent at least Core.Hello, Core.Supports.Set, and a NAWS frame.
        sb_options = [(opt, payload) for kind, opt, payload in reply_events if kind == "sb"]
        gmcp_modules = [parse_gmcp(p)[0] for opt, p in sb_options if opt == OPT_GMCP]
        assert "Core.Hello" in gmcp_modules
        assert "Core.Supports.Set" in gmcp_modules
        naws_payloads = [p for opt, p in sb_options if opt == OPT_NAWS]
        assert naws_payloads  # NAWS was sent immediately after WILL NAWS
