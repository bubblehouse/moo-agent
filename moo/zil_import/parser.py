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
    r"(?P<atom>[A-Za-z0-9_.?!*#+=\-/][A-Za-z0-9_.?!*#+=\-/]*)"
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
    return tokens


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
            return tok.value.upper()

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
