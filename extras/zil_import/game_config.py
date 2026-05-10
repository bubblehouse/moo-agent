"""
Game-specific configuration for the ZIL importer.

The translator and generator are game-agnostic by design (per
``AGENTS.md``), but the output bootstrap is necessarily
game-specific: banner text, dataset name, NPC atom-to-object
mappings.  This module is the seam between the two — every
Zork-specific string in the translator/generator is sourced from
a ``GameConfig`` instance instead of being hardcoded.

Default instance ``ZORK1_CONFIG`` configures the Zork 1 importer.
A second game would land its own ``GameConfig`` here (or in a
caller-supplied module) and pass it to ``generate_all`` /
``ZilTranslator`` without touching the engines.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class GameConfig:
    """
    Per-game knobs the translator and generator read at runtime.

    :ivar name: Human-readable game name (used in docstrings and banners).
    :ivar dataset_name: Bootstrap dataset key — also the directory
        name under ``moo/bootstrap/`` and the value passed to
        ``bootstrap.initialize_dataset(...)`` and
        ``pytest.mark.parametrize("t_init", [...])``.
    :ivar banner: Multi-line banner emitted by the bootstrap loader.
        ``{rooms}`` and ``{objects}`` placeholders are filled in by
        the generator.
    :ivar manifest_files: Names of the canonical ZIL source files
        (used in the bootstrap docstring).
    :ivar license_blurb: Licensing/credit paragraph for the bootstrap
        module docstring.
    :ivar npc_atom_map: ZIL NPC atoms → DjangoMOO object names.  The
        translator merges this into its global atom→Python-expr map
        so ``,THIEF`` / ``,TROLL`` etc. compile to the right
        ``lookup("...")`` call.
    :ivar zork_number: Numeric ZORK-NUMBER constant used by Infocom
        titles to gate text variants in shared source files.  Only
        meaningful when translating an Infocom game with the
        ``%<COND ... ZORK-NUMBER ...>`` macro; defaults to ``1`` for
        Zork 1.  Other titles set their own value (Zork II → 2,
        Zork III → 3); games without the macro can ignore it.
    """

    name: str
    dataset_name: str
    banner: str
    manifest_files: tuple[str, ...]
    license_blurb: str
    npc_atom_map: dict[str, str] = field(default_factory=dict)
    zork_number: int = 1


ZORK1_CONFIG = GameConfig(
    name="Zork 1",
    dataset_name="zork1",
    banner=(
        "ZORK I: The Great Underground Empire\n"
        "  Original (c) Infocom, Inc. 1980; MIT-licensed source release 2025.\n"
        "  Zork is a registered trademark of Activision Publishing, Inc.\n"
        "  DjangoMOO bootstrap: {rooms} rooms, {objects} objects."
    ),
    manifest_files=("dungeon.zil", "actions.zil"),
    license_blurb=(
        "Derived from the Infocom Zork 1 source (dungeon.zil / actions.zil), released\n"
        "under the MIT License by Microsoft / Activision Publishing, Inc. in 2025.\n"
        "See LICENSE and README.md in this directory for full terms and credits.\n\n"
        "Zork is a registered trademark of Activision Publishing, Inc."
    ),
    npc_atom_map={
        "THIEF": "thief",
        "ROBBER": "thief",
        "CYCLOPS": "cyclops",
        "TROLL": "troll",
        "DEMON": "demon",
        "VAMPIRE": "vampire bat",
    },
)
