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
    :ivar reset_body_filename: Filename (under ``moo/zil_import/scripts/``)
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
    :ivar adjective_expansions: Same shape as ``synonym_expansions`` but
        applied to ADJECTIVE atoms.  ZIL truncates adjective atoms the
        same way (``DEMOLI`` for ``demolition``, ``OFFICI`` for
        ``official``).  Used by the generator when emitting cross-product
        ``<adj> <syn>`` multi-word aliases so ``take junk mail`` resolves.
    :ivar verb_atom_expansions: Same shape applied to verb atoms in
        ``syntax_dict``.  ZIL truncates verb atoms too (``INVENT`` for
        ``inventory``); the generator pulls the expanded form into the
        emitted dispatcher's alias list so players can type the full word.
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
    adjective_expansions: dict[str, str] = field(default_factory=dict)
    verb_atom_expansions: dict[str, str] = field(default_factory=dict)
    # Extra aliases added to the player avatar (Adventurer) object so
    # `examine <protagonist-name>` resolves. ``me``/``self``/``myself`` /
    # ``adventurer`` are added unconditionally by the template.
    avatar_aliases: tuple[str, ...] = ()
    # Extra ZIL routine names to suppress from the auto-emit FOR THIS GAME
    # ONLY, on top of the global ``_SKIP_ROUTINES``.  Use when a routine
    # exists in more than one game but only one game needs a hand-written
    # override (a global skip would drop the routine for every game).  Each
    # listed name MUST have a per-game replacement under ``verbs/<dataset>/``
    # or the game loses the verb.
    skip_routines: frozenset[str] = frozenset()


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
    # Canonical HHG FINISH shows the score then offers RESTART/RESTORE/QUIT
    # and ends the session.  DjangoMOO is a persistent world with no session
    # restart, so the auto-translated finish() printed an unsupported prompt
    # and RETURNED — leaving a just-killed player standing alive where they
    # died (the demolition / drunk / groggy / brick / ramp deaths all funnel
    # through FINISH and so never respawned; only <JIGS-UP> deaths, which
    # route to verbs/system/death.py, teleported home).  Skip the auto-emit
    # and let verbs/hhg/thing/score/finish.py respawn at player_start so every
    # HHG death is consistent.  Zork keeps its generated FINISH (terminal for
    # the suicidal-maniac / quit cases; its JIGS-UP respawns directly).
    skip_routines=frozenset({"FINISH"}),
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
        # Heart-of-Gold endgame nouns (reachable since the `_h_prso_p`
        # direction fix). All are 6-char ZIL truncations of the word a
        # modern player types in full.
        "RECEPT": "receptacle",
        "NUTRIM": "nutrimat",
        "SUBSTI": "substitute",
        "MECHAN": "mechanism",
        "PLOTTE": "plotter",
        "DIPSWI": "dipswitch",
        "COMPUT": "computer",
        "MACHIN": "machine",
        "HANDBA": "handbag",
        "HATCHW": "hatchway",
        "BLASTE": "blaster",
        "PROBAB": "probability",
        "MAGRAT": "magrathea",
        "MESSAG": "message",
        # Nautical direction words used in Heart-of-Gold room prose
        # (``<SYNONYM EAST E STARBO SB>`` / ``<SYNONYM NORTH N FORE F
        # FOREWA>``).  Their full forms become extra exit aliases so
        # `starboard` / `forward` work, not just the 6-char truncation.
        "STARBO": "starboard",
        "FOREWA": "forward",
    },
    # ZIL ADJECTIVE atoms truncated to 6 chars.  Expanded forms become
    # the second half of player-typeable phrases like "junk mail" /
    # "demolition order" / "depressed marvin" via the generator's
    # `<adj> <syn>` cross-product emission.
    adjective_expansions={
        "DEMOLI": "demolition",
        "OFFICI": "official",
        "DEPRES": "depressed",
        "PARANO": "paranoid",
        "INCRED": "incredible",
        "FERTIL": "fertile",
        "SUCCUL": "succulent",
        "SERVIC": "service",
        "SENSIT": "sensitive",
        "DISPEN": "dispenser",
        "CIRCUI": "circuit",
        "MICROS": "microscopic",
        "PRINTE": "printed",
        "SEVENT": "seventh",
        "ADVANC": "advanced",
        "SHIPPI": "shipping",
        "PRESID": "presidential",
        "SHIPBO": "shipboard",
        "OVERRI": "override",
        "INFINI": "infinite",
        "IMPROB": "improbability",
        "PORTAB": "portable",
        "GENERA": "general",
        "SPLITT": "splitting",
        "BLINDI": "blinding",
        "FOREIG": "foreign",
        "BULLDO": "bulldozer",
        "WRECKI": "wrecking",
        "DIGITA": "digital",
        "LEATHE": "leather",
        "UNINVI": "uninviting",
        "CONSTR": "construction",
        "SANTRA": "santraginus",
        "MINERA": "mineral",
        "UNWASH": "unwashed",
        "UNIDEN": "unidentified",
        "VENDIN": "vending",
        "APPREC": "appreciation",
        "FORMID": "formidable",
        "MENACI": "menacing",
        "CORRID": "corridor",
        "AIRLOC": "airlock",
        "MASSIV": "massive",
        "SANDST": "sandstone",
        "RAVENO": "ravenous",
        "BUGBLA": "bugblatter",
        "NUTRIM": "nutrimatic",
        "COMPUT": "computer",
        "HORRIB": "horrible",
        "BEWEAP": "beweaponed",
        "APPROA": "approaching",
        "UNREGA": "unregarded",
        "SQUISH": "squishy",
        "PAINFU": "painful",
        "DISTAN": "distant",
        "FLATHE": "flathead",
        "ASSIST": "assisted",
        "PLASMI": "plasmic",
        "HYPERS": "hypersonic",
        "MOLECU": "molecular",
        "HYPERW": "hyperweave",
        "DIFFUS": "diffusion",
        "ASTERO": "asteroid",
        "ELECTR": "electronic",
        "BLINKI": "blinking",
        "HITCHH": "hitchhiker",
        "LIFETI": "lifetime",
        "MAGNIF": "magnifying",
        "AUTOPI": "autopilot",
        "TOWERI": "towering",
        "IRRITA": "irritating",
        "STRANG": "strange",
        "SYNAPS": "synapse",
        "HATCHW": "hatchway",
        "DOMED": "domed",
    },
    # ZIL verb atom truncations.  The generator pulls expanded forms
    # into the dispatcher's alias list so ``inventory`` matches alongside
    # the truncated ``invent`` atom.
    verb_atom_expansions={
        "INVENT": "inventory",
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


# ---------------------------------------------------------------------------
# Stub configs for the multi-game porting effort (2026-06-04).
#
# zork2 / zork3 are the classic-engine sequels (same EZIP family as zork1),
# expected to translate much like it.  NPC maps and synonym/adjective
# truncation tables start empty and get populated during shakedown.
#
# zorkzero / beyondzork are YZIP (later Z-machine, graphics; beyondzork adds
# RPG stats + on-screen map + a custom parser).  These are scaffold-only —
# no regen has been attempted; see each skill's *-FEASIBILITY.md.
# ---------------------------------------------------------------------------

ZORK2_CONFIG = GameConfig(
    name="Zork 2",
    dataset_name="zork2",
    banner=(
        "ZORK II: The Wizard of Frobozz\n"
        "  Original (c) Infocom, Inc. 1981; MIT-licensed source release 2025.\n"
        "  Zork is a registered trademark of Activision Publishing, Inc.\n"
        "  DjangoMOO bootstrap: {rooms} rooms, {objects} objects."
    ),
    manifest_files=("zork2.zil",),
    license_blurb=(
        "Derived from the Infocom Zork II source (2dungeon.zil / 2actions.zil and\n"
        "the shared g*.zil parser files), released under the MIT License by\n"
        "Microsoft / Activision Publishing, Inc. in 2025.  See LICENSE and\n"
        "README.md in this directory for full terms and credits.\n\n"
        "Zork is a registered trademark of Activision Publishing, Inc."
    ),
    zork_number=2,
    # ZIL NPC atoms → exact generated object names (verified live on
    # zork2.local).  Disambiguates the ones with a global twin sharing the
    # bare alias (``unicorn`` / ``princess`` both exist as a real NPC *and*
    # a GLOBAL-* scenery object), so ``,UNICORN`` in a routine resolves to
    # the NPC, not the lowest-PK alias collision.  Populated as scenes are
    # reached during shakedown.
    npc_atom_map={
        "UNICORN": "unicorn (UNICORN)",
        "GLOBAL-UNICORN": "unicorn (GLOBAL-UNICORN)",
        "PRINCESS": "beautiful princess (PRINCESS)",
        "GLOBAL-PRINCESS": "beautiful princess (GLOBAL-PRINCESS)",
        "DRAGON": "huge red dragon",
        "CERBERUS": "three-headed dog (CERBERUS)",
        "SERPENT": "baby sea serpent",
        "GNOME": "Volcano Gnome",
        "GNOME-OF-ZURICH": "Gnome of Zurich",
        "ROBOT": "robot",
        "GENIE": "demon",  # the GENIE object renders as "demon" (genie/djinn aliases)
        "WIZARD": "Wizard of Frobozz",
    },
    reset_body_filename="_zork2_reset_state_body.py",
)

ZORK3_CONFIG = GameConfig(
    name="Zork 3",
    dataset_name="zork3",
    banner=(
        "ZORK III: The Dungeon Master\n"
        "  Original (c) Infocom, Inc. 1982; MIT-licensed source release 2025.\n"
        "  Zork is a registered trademark of Activision Publishing, Inc.\n"
        "  DjangoMOO bootstrap: {rooms} rooms, {objects} objects."
    ),
    manifest_files=("zork3.zil",),
    license_blurb=(
        "Derived from the Infocom Zork III source (3dungeon.zil / 3actions.zil and\n"
        "the shared g*.zil parser files), released under the MIT License by\n"
        "Microsoft / Activision Publishing, Inc. in 2025.  See LICENSE and\n"
        "README.md in this directory for full terms and credits.\n\n"
        "Zork is a registered trademark of Activision Publishing, Inc."
    ),
    zork_number=3,
    npc_atom_map={},
)

ZORKZERO_CONFIG = GameConfig(
    name="Zork Zero",
    dataset_name="zorkzero",
    banner=(
        "ZORK ZERO: The Revenge of Megaboz\n"
        "  Original (c) Infocom, Inc. 1988.\n"
        "  Zork is a registered trademark of Activision Publishing, Inc.\n"
        "  DjangoMOO bootstrap: {rooms} rooms, {objects} objects."
    ),
    # YZIP manifest is zork0.zil (<VERSION YZIP>).  SCAFFOLD-ONLY: no regen
    # attempted; the importer targets the classic EZIP family.  See
    # extras/skills/zorkzero-shakedown/ZORKZERO-FEASIBILITY.md.
    manifest_files=("zork0.zil",),
    license_blurb=(
        "Derived from the Infocom Zork Zero source (YZIP).  Scaffold-only —\n"
        "this dataset has not been generated; the importer targets the classic\n"
        "EZIP family and has not been validated against YZIP titles.\n\n"
        "Zork is a registered trademark of Activision Publishing, Inc."
    ),
)

BEYONDZORK_CONFIG = GameConfig(
    name="Beyond Zork",
    dataset_name="beyondzork",
    banner=(
        "BEYOND ZORK: The Coconut of Quendor\n"
        "  Original (c) Infocom, Inc. 1987.\n"
        "  Zork is a registered trademark of Activision Publishing, Inc.\n"
        "  DjangoMOO bootstrap: {rooms} rooms, {objects} objects."
    ),
    # XZIP (v5) manifest is beyond.zil (z.zil is a near-identical variant).
    # SCAFFOLD-ONLY: no regen attempted — beyondzork layers RPG stats, an
    # on-screen map, and a custom parser on top of the later Z-machine.  See
    # extras/skills/beyondzork-shakedown/BEYONDZORK-FEASIBILITY.md.
    manifest_files=("beyond.zil",),
    license_blurb=(
        "Derived from the Infocom Beyond Zork source (YZIP).  Scaffold-only —\n"
        "this dataset has not been generated; the importer targets the classic\n"
        "EZIP family and has not been validated against YZIP titles.\n\n"
        "Zork is a registered trademark of Activision Publishing, Inc."
    ),
)


# Registry of known game configs keyed by ``dataset_name``.  ``cli.py``
# resolves ``--game-config <slug>`` through this map.
GAME_CONFIGS: dict[str, GameConfig] = {
    ZORK1_CONFIG.dataset_name: ZORK1_CONFIG,
    HHG_CONFIG.dataset_name: HHG_CONFIG,
    ZORK2_CONFIG.dataset_name: ZORK2_CONFIG,
    ZORK3_CONFIG.dataset_name: ZORK3_CONFIG,
    ZORKZERO_CONFIG.dataset_name: ZORKZERO_CONFIG,
    BEYONDZORK_CONFIG.dataset_name: BEYONDZORK_CONFIG,
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
