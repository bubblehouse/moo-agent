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

# ACTORBIT atoms that name player-character placeholders (not real NPCs).
# Default set covers Zork 1; HHG and other titles override via GameConfig.
_DEFAULT_PLAYER_AVATAR_ATOMS: frozenset[str] = frozenset({"ME", "ADVENTURER", "PLAYER", "WINNER"})


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
    :ivar exit_condition_overrides: Game-specific exit guards keyed on
        ``(room_atom, direction)``.  The canonical ZIL emits room
        ACTION routines that block movement on flags (TROLL-MELEE blocks
        all four exits while TROLL-FLAG is set); the auto-translator
        only catches per-direction CEXIT/FEXIT guards.  This map lets a
        game force a condition_flag + nogo_msg on the generated exit
        when the ACTION-based guard would have caught it.
    :ivar player_avatar_atoms: ZIL ACTORBIT atoms that name the
        player-character placeholder rather than a real NPC (ME,
        ADVENTURER for Zork; ARTHUR, FORD, TRILLIAN, ZAPHOD for HHG).
        These keep ``Actor`` as their parent so they don't get
        an anonymous ``Player`` row.
    :ivar reset_body_filename: Filename (under ``extras/zil_import/scripts/``)
        whose contents become the generated ``099_reset_state.py``.
        Defaults to Zork's ``_reset_state_body.py`` for back-compat; HHG
        overrides to its own ``_hhg_reset_state_body.py``.
    :ivar synonym_expansions: Per-game alias-expansion map.  ZIL
        truncates dictionary entries to 6 chars (``ASPIRI`` stands for
        ``aspirin``, ``ANALGE`` for ``analgesic``).  The generator adds
        the value as an extra alias on any object whose synonym list
        contains the key, so player-typed full words still parse.
        Keys are uppercase truncated ZIL atoms; values are full-word
        lowercase aliases.
    """

    name: str
    dataset_name: str
    banner: str
    manifest_files: tuple[str, ...]
    license_blurb: str
    npc_atom_map: dict[str, str] = field(default_factory=dict)
    zork_number: int = 1
    exit_condition_overrides: dict[tuple[str, str], tuple[str, str]] = field(default_factory=dict)
    player_avatar_atoms: frozenset[str] = _DEFAULT_PLAYER_AVATAR_ATOMS
    reset_body_filename: str = "_reset_state_body.py"
    synonym_expansions: dict[str, str] = field(default_factory=dict)
    # Extra aliases added to the player avatar (Adventurer) object so
    # `examine <protagonist-name>` resolves. ``me``/``self``/``myself`` /
    # ``adventurer`` are added unconditionally by the template.
    avatar_aliases: tuple[str, ...] = ()


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
    exit_condition_overrides={
        # TROLL-MELEE's <COND (<NOT <FSET? ,TROLL ,FIGHTBIT>> ...)> blocks
        # ALL exits while TROLL-FLAG is set, but the auto-translator only
        # finds the explicit east/west CEXIT guards.  Force south too —
        # canonical Zork has the troll cover the cellar retreat as well.
        ("TROLL-ROOM", "SOUTH"): (
            "TROLL-FLAG",
            "The troll fends you off with a menacing gesture.",
        ),
    },
)


HHG_CONFIG = GameConfig(
    name="Hitchhiker's Guide",
    dataset_name="hhg",
    banner=(
        "The Hitchhiker's Guide to the Galaxy\n"
        "  (c) 1984 Infocom, Inc.  By Douglas Adams and Steve Meretzky.\n"
        "  DjangoMOO bootstrap: {rooms} rooms, {objects} objects.\n"
        "  Source is not under an open license; used here for research only."
    ),
    # HHG's manifest at /Users/philchristensen/Workspace/hitchhikersguide/s4.zil
    # walks ``misc.zil`` / ``heart.zil`` / ``parser.zil`` / ``syntax.zil`` /
    # ``verbs.zil`` / ``earth.zil`` / ``vogon.zil`` / ``unearth.zil`` /
    # ``globals.zil`` via ``<INSERT-FILE>``.
    manifest_files=("s4.zil",),
    license_blurb=(
        "Derived from the Infocom Hitchhiker's Guide source (s4.zil and includes).\n"
        "Source is not under an open license — this dataset is generated for\n"
        "research and translator-feasibility work only.  Do not redistribute.\n\n"
        "The Hitchhiker's Guide to the Galaxy is a trademark of the Estate of\n"
        "Douglas Adams; ZIL source (c) 1984 Infocom, Inc."
    ),
    # HHG's multi-POV `IDENTITY-FLAG` mechanic switches the protagonist
    # between Arthur, Ford, Trillian, and Zaphod.  These atoms must NOT
    # route through the NPC parent (which would assign anonymous Player
    # rows that collide with the connected player).
    player_avatar_atoms=frozenset({"ME", "ARTHUR", "FORD", "TRILLIAN", "ZAPHOD"}),
    reset_body_filename="_hhg_reset_state_body.py",
    # ZIL truncates dictionary entries to 6 chars; HHG has a handful of
    # synonyms where the full English word is what a modern player will
    # actually type. Add aliases so `take aspirin` resolves alongside
    # `take aspiri`.
    synonym_expansions={
        "ASPIRI": "aspirin",
        "ANALGE": "analgesic",
        "WASHBA": "washbasin",
        "WALLPA": "wallpaper",
        "TELEPH": "telephone",
        "RECEIV": "receiver",
        "TOOTHB": "toothbrush",
        "SCREWD": "screwdriver",
        "CURTAI": "curtains",
        "BATTER": "battery",
        "BUFFER": "buffered",
        "DRESSI": "dressing",
        "PROTAG": "protagonist",
    },
    # Intentionally no identity aliases on the avatar.  HHG's multi-POV
    # IDENTITY-FLAG cycles through Arthur, Ford, Trillian, Zaphod, but
    # several of those names also belong to separate NPCs in scope at
    # different points (Ford in the Pub, Zaphod/Trillian on the Heart
    # of Gold).  Aliasing every identity name to the avatar makes the
    # parser resolve those NPCs to self ("There's nothing special about
    # yourself.") and hides identity dispatch.  Players should use
    # ``examine self`` / ``examine me`` for self-reference; identity
    # names route to whichever NPC is in scope.
    avatar_aliases=(),
)


# Registry of known game configs keyed by ``dataset_name``.  ``cli.py``
# resolves ``--game-config <slug>`` through this map.
GAME_CONFIGS: dict[str, GameConfig] = {
    ZORK1_CONFIG.dataset_name: ZORK1_CONFIG,
    HHG_CONFIG.dataset_name: HHG_CONFIG,
}


def resolve_game_config(slug: str) -> GameConfig:
    """
    Resolve a game-config slug (``dataset_name``) to its ``GameConfig``.

    :param slug: The ``dataset_name`` of a registered config (``"zork1"``).
    :returns: The matching ``GameConfig``.
    :raises KeyError: When ``slug`` is not registered.
    """
    try:
        return GAME_CONFIGS[slug]
    except KeyError as exc:
        known = ", ".join(sorted(GAME_CONFIGS)) or "(none)"
        raise KeyError(f"Unknown game-config {slug!r}; known: {known}") from exc
