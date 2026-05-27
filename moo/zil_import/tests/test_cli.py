"""CLI tests.

Smoke-level coverage for ``cli.py``: manifest expansion (the
``<INSERT-FILE …>`` recursive walk) and arg parsing.  The full
``main()`` exercises tokenize → parse → extract → generate, which is
already covered by the per-module tests; only the bits unique to the
CLI live here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from moo.zil_import.cli import _expand_manifest


def _write(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def test_expand_manifest_inlines_insert_file_chain(tmp_path: Path):
    """A top-level manifest carrying ``<INSERT-FILE "child">`` resolves to
    the manifest itself plus the child."""
    child = _write(tmp_path, "child.zil", '<TELL "child" CR>')
    manifest = _write(tmp_path, "main.zil", '<INSERT-FILE "child">')

    result = _expand_manifest([str(manifest)])
    assert result == [str(manifest.resolve()), str(child.resolve())]


def test_expand_manifest_keeps_setg_carrying_manifest(tmp_path: Path):
    """Manifests aren't dropped — they may carry top-level ``<SETG …>`` like
    ``<SETG ZORK-NUMBER 1>`` that initializes zstate slots.  Without the
    manifest in the output list, those globals would be silently lost."""
    child = _write(tmp_path, "child.zil", '<TELL "child" CR>')
    manifest = _write(
        tmp_path,
        "main.zil",
        '<SETG ZORK-NUMBER 1> <INSERT-FILE "child">',
    )
    result = _expand_manifest([str(manifest)])
    assert str(manifest.resolve()) in result
    assert str(child.resolve()) in result


def test_expand_manifest_dedupes_repeat_visits(tmp_path: Path):
    """Two manifests pointing at the same child only emit the child once."""
    child = _write(tmp_path, "child.zil", '<TELL "x" CR>')
    a = _write(tmp_path, "a.zil", '<INSERT-FILE "child">')
    b = _write(tmp_path, "b.zil", '<INSERT-FILE "child">')
    result = _expand_manifest([str(a), str(b)])
    assert result.count(str(child.resolve())) == 1


def test_expand_manifest_handles_zil_extension_already_present(tmp_path: Path):
    """``<INSERT-FILE "child.zil">`` (with extension) must not produce
    ``child.zil.zil``."""
    child = _write(tmp_path, "child.zil", '<TELL "x" CR>')
    manifest = _write(tmp_path, "main.zil", '<INSERT-FILE "child.zil">')
    result = _expand_manifest([str(manifest)])
    assert str(child.resolve()) in result
    assert not any(p.endswith(".zil.zil") for p in result)


def test_expand_manifest_real_file_with_no_inserts_passes_through(tmp_path: Path):
    """A leaf ZIL file (no ``<INSERT-FILE>`` directives) returns just itself."""
    leaf = _write(tmp_path, "leaf.zil", "<ROUTINE FOO () <RTRUE>>")
    result = _expand_manifest([str(leaf)])
    assert result == [str(leaf.resolve())]


def test_expand_manifest_missing_child_raises_oserror(tmp_path: Path):
    """``<INSERT-FILE "missing">`` propagates the OSError from parse_file
    so the CLI can surface a useful error to the operator."""
    manifest = _write(tmp_path, "main.zil", '<INSERT-FILE "missing">')
    with pytest.raises(OSError):
        _expand_manifest([str(manifest)])
