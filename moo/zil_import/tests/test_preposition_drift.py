"""
Drift guard for the generator's hand-copied preposition list.

``moo/zil_import/generator`` stays standalone (no Django import at
generation time), so ``_MOO_PREP_NAMES`` is a hand-copied flattening of
moo-core's canonical ``moo.settings.base.PREPOSITIONS``.  This test
couples the copy to its source at test time only, skipping when
moo-core's settings aren't importable (the namespace-package
``moo.settings`` lives in django-moo, not moo-agent).
"""

from __future__ import annotations

import pytest

from moo.zil_import.generator import _MOO_PREP_NAMES


def test_moo_prep_names_match_canonical_prepositions():
    """``_MOO_PREP_NAMES`` must equal the flattened ``PREPOSITIONS`` set."""
    try:
        from moo.settings.base import PREPOSITIONS
    except Exception as exc:  # pylint: disable=broad-except
        pytest.skip(f"moo.settings.base not importable in this env: {exc}")
    canonical = {prep for group in PREPOSITIONS for prep in group}
    assert set(_MOO_PREP_NAMES) == canonical
