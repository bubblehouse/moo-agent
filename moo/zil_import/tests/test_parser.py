"""Tokenizer and parser tests.

The translator suite already exercises a few parser quirks (``0?``/``1?``
tokens, string-vs-atom distinction).  These tests pin the rest of the
parser contract: comment discard, escape sequences, the division-operator
fix, multi-line strings, and parse-error handling on malformed input.
"""

from __future__ import annotations

import pytest

from moo.zil_import.parser import ParseError, Str, parse, tokenize


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "src,kinds",
    [
        ("<>", ["nil"]),
        ("123", ["number"]),
        ("-42", ["number"]),
        ("FOO", ["atom"]),
        ('"hello"', ["string"]),
        ("(A B)", ["open_paren", "atom", "atom", "close_paren"]),
        ("<X>", ["open_angle", "atom", "close_angle"]),
    ],
)
def test_tokenize_basic_kinds(src, kinds):
    tokens = tokenize(src)
    assert [t.kind for t in tokens] == kinds


def test_tokenize_division_operator_kept_intact():
    """``</ A B>`` must tokenize as a single ``/`` atom rather than being
    silently dropped.  Without this, the parser turned ``</ ,SCORE
    ,SCORE-MAX>`` into ``[,SCORE ,SCORE-MAX]``."""
    tokens = tokenize("</ A B>")
    kinds = [t.kind for t in tokens]
    assert kinds == ["open_angle", "atom", "atom", "atom", "close_angle"]
    assert tokens[1].value == "/"


def test_tokenize_escape_sequence_preserves_following_char():
    """``\\,`` ``\\"`` ``\\.`` are escape atoms — single-char tokens carrying
    the escaped character.  The parser unwraps them via the ``escape`` token
    branch."""
    tokens = tokenize(r"<BUZZ \, \" \. >")
    escapes = [t for t in tokens if t.kind == "escape"]
    assert [t.value for t in escapes] == ["\\,", '\\"', "\\."]


def test_tokenize_multiline_string_with_pipe():
    """The ``|`` inside a string literal becomes a newline at parse time.
    The tokenizer just captures the raw quoted blob."""
    tokens = tokenize('"line one|line two"')
    assert len(tokens) == 1
    assert tokens[0].kind == "string"


def test_tokenize_predicate_zero_question():
    """``0?`` and ``1?`` must lex as single atoms; documented in the
    translator suite already, anchored here as the parser-level contract."""
    tokens = tokenize("<0? .X>")
    kinds = [t.kind for t in tokens]
    assert kinds == ["open_angle", "atom", "atom", "close_angle"]
    assert tokens[1].value == "0?"


def test_radix_literal_binary_folds_to_int():
    """ZIL ``#2 <bits>`` binary literals fold to their integer value (the exit-kind
    constants — CONNECT #2 001000000000 = 512 — depend on this)."""
    assert parse(tokenize("<CONSTANT CONNECT #2 001000000000>")) == [["CONSTANT", "CONNECT", 512]]
    assert parse(tokenize("<CONSTANT SCONNECT #2 001100000000>")) == [["CONSTANT", "SCONNECT", 768]]


def test_radix_literal_leaves_decimal_and_negative_intact():
    """Plain decimal / negative numbers are unaffected by the radix fold."""
    assert parse(tokenize("<CONSTANT FOO 512>")) == [["CONSTANT", "FOO", 512]]
    assert parse(tokenize("<CONSTANT NEG -5>")) == [["CONSTANT", "NEG", -5]]


def test_decl_type_annotation_stripped_keeps_initial_value():
    """A ``NAME:TYPE`` ZIL DECL drops the declared type so the real initial value
    lands in the value slot (``<GLOBAL DWIDTH:NUMBER 0>`` must seed ``0``, not the
    string ``"NUMBER"``).  Beyond Zork's display globals depend on this."""
    assert parse(tokenize("<GLOBAL DWIDTH:NUMBER 0>")) == [["GLOBAL", "DWIDTH", 0]]
    assert parse(tokenize("<GLOBAL DMODE:FLAG T>")) == [["GLOBAL", "DMODE", "T"]]
    assert parse(tokenize("<GLOBAL VT220:FLAG <>>")) == [["GLOBAL", "VT220", None]]
    assert parse(tokenize("<GLOBAL MAPX:NUMBER ,CENTERX>")) == [["GLOBAL", "MAPX", "CENTERX"]]
    # Plain (un-typed) globals are unchanged.
    assert parse(tokenize("<GLOBAL FOO 100>")) == [["GLOBAL", "FOO", 100]]


# ---------------------------------------------------------------------------
# Parser — comment discard, nil retention
# ---------------------------------------------------------------------------


def test_parse_top_level_semicolon_comment_discarded():
    """``;EXPR`` at the top level drops the following expression entirely."""
    nodes = parse(tokenize('<TELL "kept" CR> ;<TELL "dropped" CR>'))
    assert len(nodes) == 1
    assert nodes[0][0] == "TELL"
    assert nodes[0][1] == "kept"


def test_parse_inline_semicolon_comment_does_not_drop_following_form():
    """A ``;EXPR`` inside a form discards only the immediately following
    expression — subsequent siblings in the form must be retained."""
    nodes = parse(tokenize("<COND ;<dropped> (T <RTRUE>)>"))
    assert len(nodes) == 1
    cond = nodes[0]
    assert cond[0] == "COND"
    # The (T <RTRUE>) clause is preserved; the ;<dropped> is gone.
    assert any(isinstance(c, tuple) and c and c[0] == "T" for c in cond[1:])


def test_parse_nil_token_retained_inside_forms():
    """``<>`` (nil) appears as ``None`` in the AST.  Trailing-RFALSE in verb
    bodies depends on this — losing nils silently drops the implicit return.
    """
    nodes = parse(tokenize("<COND (T <>)>"))
    assert len(nodes) == 1
    cond = nodes[0]
    clause = cond[1]
    assert isinstance(clause, tuple)
    assert clause[0] == "T"
    assert clause[1] is None


def test_parse_string_returns_str_subclass():
    """Quoted strings must round-trip as ``Str`` so the translator can tell
    them apart from bare atoms."""
    nodes = parse(tokenize('"hello"'))
    assert len(nodes) == 1
    assert isinstance(nodes[0], Str)
    assert nodes[0] == "hello"


def test_parse_string_pipe_becomes_newline():
    """The ``|`` character inside a string literal decodes to ``\\n`` at
    parse time — the tokenizer keeps it raw."""
    nodes = parse(tokenize('"first|second"'))
    assert nodes[0] == "first\nsecond"


def test_parse_string_backslash_escape_strips_slash():
    """``\\X`` inside a string yields the bare character ``X`` after parse."""
    nodes = parse(tokenize(r'"a\"b"'))
    assert nodes[0] == 'a"b'


# ---------------------------------------------------------------------------
# Parser — error paths
# ---------------------------------------------------------------------------


def test_parse_unterminated_form_raises():
    with pytest.raises(ParseError, match="Unterminated"):
        parse(tokenize("<FOO BAR"))


def test_parse_unterminated_group_raises():
    with pytest.raises(ParseError, match="Unterminated"):
        parse(tokenize("(FOO BAR"))


def test_parse_stray_close_angle_raises():
    with pytest.raises(ParseError, match="Unexpected '>'"):
        parse(tokenize(">"))


def test_parse_stray_close_paren_raises():
    with pytest.raises(ParseError, match="Unexpected '\\)'"):
        parse(tokenize(")"))


def test_parse_dangling_semicolon_at_close_is_no_op():
    """A ``;`` immediately before ``>`` or ``)`` (no expression to discard)
    is silently skipped — the existing parser swallows the semicolon and
    keeps going.  Anchors that no exception is raised."""
    nodes = parse(tokenize("<FOO ;>"))
    assert nodes == [["FOO"]]
