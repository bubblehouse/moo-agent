# -*- coding: utf-8 -*-
"""
Client-side IAC (telnet subnegotiation) parser, encoder, and negotiator.
Mirrors the server's ``moo/shell/iac.py`` from the client role. See
``docs/source/explanation/agent-internals.md`` (IAC) for the design narrative.
"""

from __future__ import annotations

import json
import logging
from typing import Callable, Optional

log = logging.getLogger(__name__)

# --- Control bytes ----------------------------------------------------------

IAC = 0xFF
DONT = 0xFE
DO = 0xFD
WONT = 0xFC
WILL = 0xFB
SB = 0xFA
GA = 0xF9
EL = 0xF8
EC = 0xF7
AYT = 0xF6
AO = 0xF5
IP = 0xF4
BRK = 0xF3
DM = 0xF2
NOP = 0xF1
SE = 0xF0
EOR = 0xEF

# --- Options ---------------------------------------------------------------

OPT_BINARY = 0
OPT_ECHO = 1
OPT_SGA = 3
OPT_TTYPE = 24
OPT_EOR_OPT = 25
OPT_NAWS = 31
OPT_LINEMODE = 34
OPT_CHARSET = 42
OPT_MSSP = 70
OPT_MSP = 90
OPT_GMCP = 201

# TTYPE subnegotiation commands (RFC 1091)
TTYPE_IS = 0
TTYPE_SEND = 1

# CHARSET subnegotiation commands (RFC 2066)
CHARSET_REQUEST = 1
CHARSET_ACCEPTED = 2
CHARSET_REJECTED = 3

# MSSP variable/value separators
MSSP_VAR = 1
MSSP_VAL = 2

# MTTS capability bitfield values.
# https://tintin.mudhalla.net/protocols/mtts/
MTTS_ANSI = 1
MTTS_VT100 = 2
MTTS_UTF8 = 4
MTTS_256_COLORS = 8
MTTS_MOUSE_TRACKING = 16
MTTS_OSC_COLOR_PALETTE = 32
MTTS_SCREEN_READER = 64
MTTS_PROXY = 128
MTTS_TRUECOLOR = 256
MTTS_MNES = 512
MTTS_MSLP = 1024

# ANSI + UTF-8 + 256-color + screen-reader (we read output programmatically).
DEFAULT_MTTS = MTTS_ANSI | MTTS_UTF8 | MTTS_256_COLORS | MTTS_SCREEN_READER

# --- Parser -----------------------------------------------------------------


class IacParser:
    """
    Byte-feed state machine for IAC sequences. Identical to server's
    ``moo/shell/iac.py:IacParser``.

    Feed raw bytes via :meth:`feed`; get back ``(events, residual)``.
    Partial frames across calls are buffered internally.

    Events:

    - ``("cmd", cmd, opt)`` — IAC WILL/WONT/DO/DONT <opt>
    - ``("sb", opt, payload_bytes)`` — IAC SB <opt> <payload> IAC SE
    - ``("ga",)`` — IAC GA
    - ``("eor",)`` — IAC EOR
    """

    _NORMAL = 0
    _IAC = 1
    _IAC_CMD = 2
    _SB_OPT = 3
    _SB_PAYLOAD = 4
    _SB_IAC = 5

    def __init__(self) -> None:
        self._state = self._NORMAL
        self._pending_cmd: int = 0
        self._sb_opt: int = 0
        self._sb_buf: bytearray = bytearray()

    def feed(self, data: bytes) -> tuple[list[tuple], bytes]:
        events: list[tuple] = []
        residual = bytearray()

        for byte in data:
            state = self._state

            if state == self._NORMAL:
                if byte == IAC:
                    self._state = self._IAC
                else:
                    residual.append(byte)

            elif state == self._IAC:
                if byte == IAC:
                    residual.append(IAC)
                    self._state = self._NORMAL
                elif byte in (WILL, WONT, DO, DONT):
                    self._pending_cmd = byte
                    self._state = self._IAC_CMD
                elif byte == SB:
                    self._state = self._SB_OPT
                elif byte == GA:
                    events.append(("ga",))
                    self._state = self._NORMAL
                elif byte == EOR:
                    events.append(("eor",))
                    self._state = self._NORMAL
                elif byte in (NOP, DM, BRK, IP, AO, AYT, EC, EL):
                    self._state = self._NORMAL
                else:
                    log.debug("unexpected byte after IAC: 0x%02x", byte)
                    self._state = self._NORMAL

            elif state == self._IAC_CMD:
                events.append(("cmd", self._pending_cmd, byte))
                self._pending_cmd = 0
                self._state = self._NORMAL

            elif state == self._SB_OPT:
                self._sb_opt = byte
                self._sb_buf = bytearray()
                self._state = self._SB_PAYLOAD

            elif state == self._SB_PAYLOAD:
                if byte == IAC:
                    self._state = self._SB_IAC
                else:
                    self._sb_buf.append(byte)

            elif state == self._SB_IAC:
                if byte == IAC:
                    self._sb_buf.append(IAC)
                    self._state = self._SB_PAYLOAD
                elif byte == SE:
                    events.append(("sb", self._sb_opt, bytes(self._sb_buf)))
                    self._sb_opt = 0
                    self._sb_buf = bytearray()
                    self._state = self._NORMAL
                else:
                    log.warning("unexpected byte 0x%02x after IAC in SB payload; aborting frame", byte)
                    self._sb_opt = 0
                    self._sb_buf = bytearray()
                    self._state = self._NORMAL

        return events, bytes(residual)


# --- Encoders ---------------------------------------------------------------


def encode_cmd(cmd: int, opt: int) -> bytes:
    return bytes((IAC, cmd, opt))


def encode_sb(opt: int, payload: bytes) -> bytes:
    """Encode IAC SB <opt> <payload> IAC SE, doubling 0xFF in payload."""
    escaped = payload.replace(bytes((IAC,)), bytes((IAC, IAC)))
    return bytes((IAC, SB, opt)) + escaped + bytes((IAC, SE))


def encode_ttype_is(value: str) -> bytes:
    return encode_sb(OPT_TTYPE, bytes((TTYPE_IS,)) + value.encode("utf-8"))


def encode_naws(width: int, height: int) -> bytes:
    payload = bytes(
        (
            (width >> 8) & 0xFF,
            width & 0xFF,
            (height >> 8) & 0xFF,
            height & 0xFF,
        )
    )
    return encode_sb(OPT_NAWS, payload)


def encode_gmcp(module: str, data) -> bytes:
    """Encode a GMCP frame: ``IAC SB GMCP "<module> <json>" IAC SE``."""
    if data is None:
        payload = module.encode("utf-8")
    else:
        payload = (module + " " + json.dumps(data, separators=(",", ":"))).encode("utf-8")
    return encode_sb(OPT_GMCP, payload)


def encode_charset_request(charsets: list[str], sep: str = " ") -> bytes:
    payload = bytes((CHARSET_REQUEST,)) + sep.encode("ascii")
    payload += sep.encode("ascii").join(c.encode("ascii") for c in charsets)
    return encode_sb(OPT_CHARSET, payload)


# --- Inbound payload parsers ------------------------------------------------


def parse_gmcp(payload: bytes) -> tuple[str, object]:
    """Inverse of :func:`encode_gmcp` — returns ``(module, data_or_None)``."""
    text = payload.decode("utf-8", errors="replace")
    space = text.find(" ")
    if space == -1:
        return text, None
    module = text[:space]
    raw = text[space + 1 :].strip()
    if not raw:
        return module, None
    return module, json.loads(raw)


def parse_ttype_subneg(payload: bytes) -> tuple[int, str]:
    """Parse a TTYPE subnegotiation payload.

    Returns ``(subcmd, value)`` where subcmd is :data:`TTYPE_IS` or
    :data:`TTYPE_SEND`. For SEND the value is empty.
    """
    if not payload:
        raise ValueError("empty TTYPE payload")
    return payload[0], payload[1:].decode("utf-8", errors="replace")


def parse_mssp(payload: bytes) -> dict[str, list[str]]:
    """Parse an MSSP payload into ``{name: [values...]}``."""
    result: dict[str, list[str]] = {}
    name = None
    cur = bytearray()
    values: list[str] = []
    mode = 0  # 0=expecting VAR, 1=in name, 2=in value

    def flush_value():
        if name is not None:
            values.append(cur.decode("utf-8", errors="replace"))

    def flush_name():
        nonlocal name
        if name is None and cur:
            name = cur.decode("utf-8", errors="replace")

    i = 0
    while i < len(payload):
        b = payload[i]
        if b == MSSP_VAR:
            if mode == 2:
                flush_value()
                if name is not None:
                    result[name] = values
            elif mode == 1:
                flush_name()
            cur = bytearray()
            values = []
            name = None
            mode = 1
        elif b == MSSP_VAL:
            if mode == 1:
                flush_name()
                cur = bytearray()
            elif mode == 2:
                flush_value()
                cur = bytearray()
            mode = 2
        else:
            cur.append(b)
        i += 1
    if mode == 2:
        flush_value()
    if name is not None:
        result[name] = values
    return result


# --- Negotiator (client-side) ----------------------------------------------


class AgentIacNegotiator:
    """
    Client-side IAC negotiator. See agent-internals: IAC for the
    handshake design, what we offer, and what we accept.
    """

    # DO X → reply WILL X.
    _WE_OFFER = frozenset({OPT_TTYPE, OPT_NAWS, OPT_CHARSET})

    # WILL X → reply DO X. MSP and SGA are intentionally excluded.
    _WE_ACCEPT_SERVER = frozenset({OPT_GMCP, OPT_MSSP, OPT_EOR_OPT, OPT_CHARSET})

    def __init__(
        self,
        client_name: str = "moo-agent",
        client_version: str = "0.1",
        terminal: str = "XTERM-256COLOR",
        naws: tuple[int, int] = (80, 24),
        mtts: int = DEFAULT_MTTS,
        gmcp_supports: Optional[list[str]] = None,
        on_gmcp: Optional[Callable[[str, object], None]] = None,
        on_mssp: Optional[Callable[[dict[str, list[str]]], None]] = None,
        on_capability_change: Optional[Callable[[dict[str, object]], None]] = None,
    ) -> None:
        self.client_name = client_name
        self.client_version = client_version
        self.terminal = terminal
        self.naws = naws
        self.mtts = mtts
        self.gmcp_supports = (
            list(gmcp_supports)
            if gmcp_supports is not None
            else [
                "Char 1",
                "Room 1",
                "Comm 1",
                "MSSP 1",
            ]
        )

        self._on_gmcp = on_gmcp
        self._on_mssp = on_mssp
        self._on_capability_change = on_capability_change

        self.capabilities: dict[str, object] = {
            "gmcp": False,
            "mssp": False,
            "eor": False,
            "charset": False,
            "ttype": False,
            "naws": False,
        }
        self._ttype_stage = 0  # 0=inactive, 1=name, 2=terminal, 3=MTTS, 4=loop
        self._gmcp_hello_sent = False
        # RFC 1143: track refusals so repeat offers are silently ignored.
        self._refused_will: set[int] = set()
        self._refused_do: set[int] = set()

    # --- Event dispatch -----------------------------------------------------

    def handle(self, event: tuple) -> bytes:
        """Dispatch a parsed IAC event; return reply bytes (possibly empty)."""
        kind = event[0]
        if kind == "cmd":
            return self._handle_cmd(event[1], event[2])
        if kind == "sb":
            return self._handle_sb(event[1], event[2])
        # GA and EOR are ignored — we use PREFIX/SUFFIX, not GA, for framing.
        return b""

    def _handle_cmd(self, cmd: int, opt: int) -> bytes:
        if cmd == WILL:
            return self._handle_will(opt)
        if cmd == WONT:
            return self._handle_wont(opt)
        if cmd == DO:
            return self._handle_do(opt)
        if cmd == DONT:
            return self._handle_dont(opt)
        return b""

    def _handle_will(self, opt: int) -> bytes:
        """
        Server announced WILL <opt>. Reply DO if accepted, DONT otherwise.
        Only reply when state actually changes to avoid negotiation loops.
        """
        label = self._opt_label(opt)
        previously = bool(self.capabilities.get(label, False)) if label else False
        if opt in self._WE_ACCEPT_SERVER:
            if previously:
                return b""
            self._mark_enabled(opt)
            reply = encode_cmd(DO, opt)
            if opt == OPT_GMCP:
                reply += self._send_gmcp_handshake()
            self._notify_capability_change()
            return reply
        if opt in self._refused_will:
            return b""
        self._refused_will.add(opt)
        return encode_cmd(DONT, opt)

    def _handle_wont(self, opt: int) -> bytes:
        """Server says WONT <opt>; ack with DONT only if previously enabled."""
        label = self._opt_label(opt)
        if label and self.capabilities.get(label):
            self._mark_disabled(opt)
            self._notify_capability_change()
            return encode_cmd(DONT, opt)
        return b""

    def _handle_do(self, opt: int) -> bytes:
        """Server asks us to enable <opt> on our side."""
        label = self._opt_label(opt)
        previously = bool(self.capabilities.get(label, False)) if label else False
        if opt in self._WE_OFFER:
            if previously:
                return b""
            if label:
                self.capabilities[label] = True
                self._notify_capability_change()
            reply = encode_cmd(WILL, opt)
            if opt == OPT_NAWS:
                # RFC 1073: send window size immediately after agreeing.
                reply += encode_naws(self.naws[0], self.naws[1])
            elif opt == OPT_TTYPE:
                # Arm the TTYPE stage so we're ready for SB TTYPE SEND.
                self._ttype_stage = 1
            return reply
        if opt in self._refused_do:
            return b""
        self._refused_do.add(opt)
        return encode_cmd(WONT, opt)

    def _handle_dont(self, opt: int) -> bytes:
        """Server tells us not to enable <opt>; acknowledge only if we had it enabled."""
        label = self._opt_label(opt)
        if label and self.capabilities.get(label):
            self.capabilities[label] = False
            self._notify_capability_change()
            return encode_cmd(WONT, opt)
        return b""

    def _handle_sb(self, opt: int, payload: bytes) -> bytes:
        if opt == OPT_TTYPE:
            return self._handle_ttype_sb(payload)
        if opt == OPT_GMCP:
            return self._handle_gmcp_sb(payload)
        if opt == OPT_MSSP:
            return self._handle_mssp_sb(payload)
        if opt == OPT_CHARSET:
            return self._handle_charset_sb(payload)
        return b""

    # --- Specific subnegotiation handlers ----------------------------------

    def _handle_ttype_sb(self, payload: bytes) -> bytes:
        try:
            subcmd, _value = parse_ttype_subneg(payload)
        except ValueError:
            return b""
        if subcmd != TTYPE_SEND:
            return b""

        # 3-stage handshake: name, terminal, MTTS bitfield. Stage 4+ loops
        # on the terminal value to signal we have nothing more to offer.
        stage = self._ttype_stage if self._ttype_stage > 0 else 1
        if stage == 1:
            self._ttype_stage = 2
            return encode_ttype_is(self.client_name)
        if stage == 2:
            self._ttype_stage = 3
            return encode_ttype_is(self.terminal)
        if stage == 3:
            self._ttype_stage = 4
            self.capabilities["ttype"] = True
            self._notify_capability_change()
            return encode_ttype_is(f"MTTS {self.mtts}")
        return encode_ttype_is(self.terminal)

    def _handle_gmcp_sb(self, payload: bytes) -> bytes:
        try:
            module, data = parse_gmcp(payload)
        except (ValueError, json.JSONDecodeError):
            log.warning("malformed GMCP payload: %r", payload)
            return b""
        if self._on_gmcp is not None:
            try:
                self._on_gmcp(module, data)
            except Exception:  # pylint: disable=broad-except
                log.exception("on_gmcp callback failed for module=%s", module)
        return b""

    def _handle_mssp_sb(self, payload: bytes) -> bytes:
        try:
            values = parse_mssp(payload)
        except Exception:  # pylint: disable=broad-except
            log.exception("malformed MSSP payload: %r", payload)
            return b""
        if self._on_mssp is not None:
            try:
                self._on_mssp(values)
            except Exception:  # pylint: disable=broad-except
                log.exception("on_mssp callback failed")
        return b""

    def _handle_charset_sb(self, payload: bytes) -> bytes:
        if not payload:
            return b""
        subcmd = payload[0]
        if subcmd != CHARSET_REQUEST:
            return b""  # ACCEPTED / REJECTED — nothing to reply
        rest = payload[1:]
        if not rest:
            return encode_sb(OPT_CHARSET, bytes((CHARSET_REJECTED,)))
        sep = rest[:1]
        choices = rest[1:].split(sep)
        for choice in choices:
            name = choice.decode("ascii", errors="ignore").strip().upper()
            if name in ("UTF-8", "UTF8"):
                return encode_sb(OPT_CHARSET, bytes((CHARSET_ACCEPTED,)) + b"UTF-8")
        return encode_sb(OPT_CHARSET, bytes((CHARSET_REJECTED,)))

    # --- GMCP handshake side effects ---------------------------------------

    def _send_gmcp_handshake(self) -> bytes:
        """After GMCP enables, send Core.Hello and Core.Supports.Set."""
        if self._gmcp_hello_sent:
            return b""
        self._gmcp_hello_sent = True
        return encode_gmcp(
            "Core.Hello",
            {"client": self.client_name, "version": self.client_version},
        ) + encode_gmcp("Core.Supports.Set", self.gmcp_supports)

    def send_gmcp(self, module: str, data) -> bytes:
        """Convenience helper for higher layers: encode a GMCP frame to send."""
        return encode_gmcp(module, data)

    # --- Capability state helpers ------------------------------------------

    def _mark_enabled(self, opt: int) -> None:
        label = self._opt_label(opt)
        if label:
            self.capabilities[label] = True

    def _mark_disabled(self, opt: int) -> None:
        label = self._opt_label(opt)
        if label:
            self.capabilities[label] = False

    def _notify_capability_change(self) -> None:
        if self._on_capability_change is not None:
            try:
                self._on_capability_change(dict(self.capabilities))
            except Exception:  # pylint: disable=broad-except
                log.exception("on_capability_change callback failed")

    @staticmethod
    def _opt_label(opt: int) -> str:
        return {
            OPT_GMCP: "gmcp",
            OPT_MSSP: "mssp",
            OPT_EOR_OPT: "eor",
            OPT_CHARSET: "charset",
            OPT_TTYPE: "ttype",
            OPT_NAWS: "naws",
        }.get(opt, "")
