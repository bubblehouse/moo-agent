"""
ZIL S-expression tokenizer and parser.

See :doc:`/reference/zil-importer` for the public API and
:doc:`/explanation/zil-importer` for the why.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Union

# A parsed node is one of these types
Atom = str  # upper-case identifier or keyword
Number = int
Nil = type(None)  # <>
Form = list  # [head, arg1, arg2, ...] — angle-bracket form
Group = tuple  # (elem, ...) — parenthesized property group


class Str(str):
    """
    A ZIL string literal — distinct from bare atoms at the type level.

    See :doc:`/reference/zil-importer` for the rationale.
    """


# `;EXPR` comment sentinel — distinct from `<>` so nil tokens still reach the translator.
_DISCARD = object()


Node = Union[str, int, None, list, tuple]


_TOKEN_RE = re.compile(
    # Non-overlapping string-body branches avoid catastrophic backtracking on long sources.
    r'(?P<string>"(?:[^"\\]|\\.)*")'
    r"|"
    # Backslash-escaped atom char: <BUZZ \, \" \.> lists comma/quote/period as buzzwords.
    r"(?P<escape>\\.)"
    r"|"
    r"(?P<nil><>)"
    r"|"
    r"(?P<open_angle><)"
    r"|"
    r"(?P<close_angle>>)"
    r"|"
    r"(?P<open_paren>\()"
    r"|"
    r"(?P<close_paren>\))"
    r"|"
    r"(?P<semicolon>;)"
    r"|"
    # See explanation/zil-importer (Why predicate atoms parse as one token).
    r"(?P<number>-?\d+(?![A-Za-z0-9_.?!*#+=\-/]))"
    r"|"
    # Atom continuation includes `/` so `</ A B>` (integer division) tokenises correctly.
    # A trailing `:TYPE` ZIL DECL (e.g. ``DWIDTH:NUMBER``) is absorbed into the atom
    # so it stays attached to its name rather than splitting off as a phantom token;
    # parse() strips the declared type, which is informational only.
    r"(?P<atom>[A-Za-z0-9_.?!*#+=\-/][A-Za-z0-9_.?!*#+=\-/]*(?::[A-Za-z0-9_.?!*#+=\-/]+)?)"
    r"|"
    r"(?P<ws>\s+)",
    re.DOTALL,
)


@dataclass
class Token:
    """One lexed ZIL token: kind, raw text, source line, and byte offset."""

    kind: str
    value: str
    line: int
    offset: int = 0  # byte offset into source, for raw_zil capture


_RADIX_RE = re.compile(r"#(\d+)$")


def _fold_radix_literals(tokens: list[Token]) -> list[Token]:
    """
    Collapse ZIL radix literals (``#<radix> <digits>``) into a single number.

    ZIL writes non-decimal numbers as a ``#N`` prefix followed by the digits,
    e.g. ``#2 001000000000`` is binary (= 512).  The lexer splits that into an
    atom token ``#2`` and a number token ``001000000000`` (read as decimal), so
    the value is lost.  Re-read the digit token in the prefix's base and emit a
    single decimal number token in its place.  A ``#N`` not followed by a valid
    digit token is left untouched.
    """
    folded: list[Token] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        match = _RADIX_RE.fullmatch(tok.value) if tok.kind == "atom" else None
        nxt = tokens[i + 1] if i + 1 < len(tokens) else None
        if match and nxt is not None and nxt.kind == "number":
            radix = int(match.group(1))
            try:
                value = int(nxt.value, radix)
            except ValueError:
                folded.append(tok)
                i += 1
                continue
            folded.append(Token(kind="number", value=str(value), line=tok.line, offset=tok.offset))
            i += 2
            continue
        folded.append(tok)
        i += 1
    return folded


def tokenize(source: str) -> list[Token]:
    """
    Tokenize ZIL source text.

    :param source: Raw ZIL source.
    :returns: List of :class:`Token` instances (whitespace dropped).
    """
    tokens = []
    line = 1
    for m in _TOKEN_RE.finditer(source):
        kind = m.lastgroup
        value = m.group()
        if kind == "ws":
            line += value.count("\n")
            continue
        tokens.append(Token(kind=kind, value=value, line=line, offset=m.start()))
        line += value.count("\n")
    return _fold_radix_literals(tokens)


class ParseError(Exception):
    """Raised on a malformed ZIL source — unmatched ``<>`` / ``()`` brackets or an unknown token."""


def _parse_string(raw: str) -> str:
    """
    Decode a ZIL string token (strip quotes, handle ``|`` newlines and ``\\`` escapes).

    :param raw: The raw string token (including surrounding quotes).
    :returns: The decoded string contents.
    """
    inner = raw[1:-1]
    result = []
    i = 0
    while i < len(inner):
        ch = inner[i]
        if ch == "\\":
            i += 1
            result.append(inner[i] if i < len(inner) else "\\")
        elif ch == "|":
            result.append("\n")
        else:
            result.append(ch)
        i += 1
    return "".join(result)


def parse(tokens: list[Token]) -> list[Node]:
    """
    Parse a flat token list into a list of top-level nodes.

    :param tokens: Token stream from :func:`tokenize`.
    :returns: Top-level AST nodes (lists, tuples, atoms, ints, ``None``).
    :raises ParseError: On unmatched ``<>`` / ``()`` brackets.
    """
    pos = 0

    def peek() -> Token | None:
        return tokens[pos] if pos < len(tokens) else None

    def consume() -> Token:
        nonlocal pos
        tok = tokens[pos]
        pos += 1
        return tok

    def parse_one() -> Node:
        tok = peek()
        if tok is None:
            raise ParseError("Unexpected end of input")

        if tok.kind == "nil":
            consume()
            return None

        if tok.kind == "number":
            consume()
            return int(tok.value)

        if tok.kind == "string":
            consume()
            return Str(_parse_string(tok.value))

        if tok.kind == "atom":
            consume()
            name = tok.value.upper()
            # Drop a ZIL DECL type annotation (``NAME:TYPE``).  The declared
            # type is informational only; without this the type atom would
            # otherwise occupy the value slot (``<GLOBAL DWIDTH:NUMBER 0>``
            # → ``["GLOBAL", "DWIDTH", "NUMBER", 0]``, seeding the literal
            # string "NUMBER" instead of 0).
            if ":" in name:
                name = name.split(":", 1)[0]
            return name

        if tok.kind == "escape":
            # Backslash-escaped single character used as a literal atom in
            # forms like ``<BUZZ \, \" >``.  Strip the backslash and return
            # the escaped character as a normal atom.
            consume()
            return tok.value[1:]

        if tok.kind == "open_angle":
            consume()
            items = []
            while True:
                t = peek()
                if t is None:
                    raise ParseError("Unterminated <...> form")
                if t.kind == "close_angle":
                    consume()
                    break
                val = parse_one()
                if val is not _DISCARD:  # filter ;-comments, keep <> (None)
                    items.append(val)
            return items  # Form

        if tok.kind == "open_paren":
            consume()
            items = []
            while True:
                t = peek()
                if t is None:
                    raise ParseError("Unterminated (...) group")
                if t.kind == "close_paren":
                    consume()
                    break
                val = parse_one()
                if val is not _DISCARD:  # filter ;-comments, keep <> (None)
                    items.append(val)
            return tuple(items)  # Group

        if tok.kind == "semicolon":
            # ZIL expression comment: `;EXPR` — consume and discard the next expression.
            # If the next token is a closer or EOF, just skip the semicolon itself.
            consume()
            nxt = peek()
            if nxt is not None and nxt.kind not in ("close_angle", "close_paren"):
                try:
                    parse_one()  # discard
                except ParseError:
                    pass
            return _DISCARD  # sentinel — filtered out by form/group construction

        if tok.kind == "close_angle":
            raise ParseError(f"Unexpected '>' at line {tok.line}")
        if tok.kind == "close_paren":
            raise ParseError(f"Unexpected ')' at line {tok.line}")

        raise ParseError(f"Unknown token {tok!r}")

    results = []
    while pos < len(tokens):
        val = parse_one()
        if val is not _DISCARD:  # drop top-level ;-comments
            results.append(val)
    return results


def parse_file(path: str) -> tuple[list[Node], str]:
    """
    Parse a ZIL source file.

    :param path: Filesystem path to the ZIL source.
    :returns: ``(nodes, source_text)`` where ``nodes`` is the AST and
        ``source_text`` is the raw file contents.
    """
    with open(path, encoding="utf-8", errors="replace") as f:
        source = f.read()
    tokens = tokenize(source)
    return parse(tokens), source
