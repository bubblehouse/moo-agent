"""
Intermediate representation dataclasses for ZIL world elements.

See :doc:`/reference/zil-importer`.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ZilExit:
    direction: str  # "NORTH", "EAST", etc.
    dest: str | None  # room atom, or None for blocked/procedural
    message: str | None  # nogo message for string-only exits
    condition: str | None  # flag atom for conditional IF exits
    else_message: str | None  # fallback message when condition is false
    per_routine: str | None  # routine name for PER exits


@dataclass
class ZilRoom:
    atom: str  # ZIL identifier (e.g. "WEST-OF-HOUSE")
    desc: str  # short title shown in room header
    ldesc: str | None  # long description body
    fdesc: str | None  # first-visit description
    exits: list[ZilExit] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    globals: list[str] = field(default_factory=list)  # globally-visible scenery atoms
    action: str | None = None  # ACTION routine name
    value: int = 0  # discovery score points
    pseudo: list[tuple[str, str]] = field(default_factory=list)  # ("word", routine) pairs


@dataclass
class ZilObject:
    atom: str  # ZIL identifier
    location: str | None  # container atom (room or object)
    synonyms: list[str] = field(default_factory=list)
    adjectives: list[str] = field(default_factory=list)
    desc: str | None = None  # short name / brief description
    ldesc: str | None = None  # long description
    fdesc: str | None = None  # first-visit description
    text: str | None = None  # readable content (books, signs)
    flags: list[str] = field(default_factory=list)
    action: str | None = None
    capacity: int = 0
    size: int = 5
    value: int = 0
    tvalue: int = 0  # treasure value toward score
    vtype: str | None = None  # vehicle-type atom (e.g. NONLANDBIT for boats)


@dataclass
class ZilRoutine:
    name: str
    params: list[str]  # positional parameters (before "AUX")
    aux_vars: list[str]  # local variables (after "AUX")
    body: list  # full parsed AST: list of body forms (form[2:])
    raw_zil: str  # repr(form) snapshot for inline comments
    # Initial values keyed by parameter / aux name (UPPER-KEBAB). Missing key
    # means the variable has no declared default (None at runtime).
    initial_values: dict = field(default_factory=dict)


@dataclass
class ZilTable:
    name: str  # global variable atom (e.g. "HERO-MELEE")
    values: list  # list of scalar entries extracted from TABLE/LTABLE


# Directions that are treated as exits in ROOM definitions
DIRECTION_ATOMS = frozenset(
    [
        "NORTH",
        "SOUTH",
        "EAST",
        "WEST",
        "NE",
        "NW",
        "SE",
        "SW",
        "UP",
        "DOWN",
        "IN",
        "OUT",
        "LAND",
    ]
)

# Direction → canonical alias for DjangoMOO exits
DIRECTION_ALIASES: dict[str, list[str]] = {
    "NORTH": ["north", "n"],
    "SOUTH": ["south", "s"],
    "EAST": ["east", "e"],
    "WEST": ["west", "w"],
    "NE": ["northeast", "ne"],
    "NW": ["northwest", "nw"],
    "SE": ["southeast", "se"],
    "SW": ["southwest", "sw"],
    "UP": ["up", "u"],
    "DOWN": ["down", "d"],
    "IN": ["in", "enter"],
    "OUT": ["out", "exit"],
    "LAND": ["land"],
}

# ZIL object flags and their DjangoMOO property mapping
FLAG_PROPERTIES: dict[str, tuple[str, object]] = {
    "TAKEBIT": ("takeable", True),
    "OPENBIT": ("open", True),
    "DOORBIT": ("is_door", True),
    "LIGHTBIT": ("lit", True),
    "BURNBIT": ("flammable", True),
    "READBIT": ("readable", True),
    "DRINKBIT": ("drinkable", True),
    "FOODBIT": ("edible", True),
    # NDESCBIT and INVISIBLE are semantically distinct in ZIL: NDESCBIT
    # suppresses auto-description in room listings (but the parser still
    # finds the object), while INVISIBLE hides the object from the parser
    # entirely.  Map NDESCBIT to its own property so PRINT-CONT's recurse
    # branch (gated on ``<NOT <FSET? .Y ,INVISIBLE>>``) fires for NDESCBIT
    # surface containers like the kitchen table.
    "NDESCBIT": ("ndescbit", True),
    "TRANSBIT": ("transparent", True),
    "WEAPONBIT": ("weapon", True),
    "FIGHTBIT": ("hostile", True),
    "VEHBIT": ("vehicle", True),
    "CLIMBBIT": ("climbable", True),
    "TURNBIT": ("turnable", True),
    "SEARCHBIT": ("searchable", True),
    # Substrate V-routines query these flags; missing entries silently
    # break behavior (V-OPEN gives "you must tell me how" if CONTBIT is
    # missing, V-LAMP-ON gives "can't turn that on" if LIGHTBIT is missing).
    "CONTBIT": ("contbit", True),
    "ACTORBIT": ("actorbit", True),
    "WEARBIT": ("wearbit", True),
    "ONBIT": ("onbit", True),
    "TOUCHBIT": ("touchbit", True),
    "FLAMEBIT": ("flamebit", True),
    "TOOLBIT": ("toolbit", True),
    "WATERBIT": ("waterbit", True),
    "TRYTAKEBIT": ("trytakebit", True),
    "VICBIT": ("vicbit", True),
    "STAGGERED": ("staggered", True),
    "DEAD": ("dead", True),
    "INVISIBLE": ("invisible", True),
    "RMUNGBIT": ("rmungbit", True),
    "SACREDBIT": ("sacred", True),
    "MAZEBIT": ("maze", True),
    "RLANDBIT": ("outdoor", True),
    # Suppress definite/indefinite article and select the "an" variant.
    # Honored by helpers/article.py; missing entries silently fall through
    # to "the <desc>" — producing "the your gown" for possessive DESCs.
    "NARTICLEBIT": ("narticlebit", True),
    "VOWELBIT": ("vowelbit", True),
}

# Room-specific flags
ROOM_FLAG_PROPERTIES: dict[str, tuple[str, object]] = {
    "ONBIT": ("dark", False),  # room is lit
    "RLANDBIT": ("outdoor", True),
    "SACREDBIT": ("sacred", True),
    "MAZEBIT": ("maze", True),
    # Vehicle-type flags.  ``GOTO`` checks ``flag(rm, av)`` where ``av``
    # is the vehicle's ``vtype`` atom (e.g. ``NONLANDBIT``).  Match the
    # boat's ``(VTYPE NONLANDBIT)`` against rooms tagged with the same
    # flag — water rooms get ``nonlandbit=True`` so ``flag(reservoir,
    # "NONLANDBIT")`` returns truthy.
    "NONLANDBIT": ("nonlandbit", True),
    "RWATERBIT": ("nonlandbit", True),
    "RAIRBIT": ("nonlandbit", True),
}

# ZIL verb atom → zork1 command verb aliases
# Used by translator for <VERB?> checks and by command verb shebang generation.
ZIL_VERBS: dict[str, list[str]] = {
    "TAKE": ["take", "get", "pick"],
    "DROP": ["drop"],
    "THROW": ["throw", "toss"],
    "PUT": ["put", "place", "insert"],
    "GIVE": ["give"],
    "OPEN": ["open"],
    "CLOSE": ["close", "shut"],
    "LOCK": ["lock"],
    "UNLOCK": ["unlock"],
    "EXAMINE": ["examine", "x", "describe", "what"],
    "READ": ["read"],
    "LOOK": ["look", "l"],
    "ATTACK": ["attack", "kill", "hit", "fight", "stab", "cut", "slice"],
    "WALK": ["go", "walk", "move"],
    "ENTER": ["enter"],
    "EXIT-ROOM": ["exit", "leave"],
    "INVENTORY": ["inventory", "i"],
    "SCORE": ["score"],
    "QUIT": ["quit", "q"],
    "RESTART": ["restart"],
    "AGAIN": ["again", "g"],
    "WAIT": ["wait", "z"],
    "DIAGNOSE": ["diagnose"],
    "VERBOSE": ["verbose"],
    "BRIEF": ["brief"],
    "SUPER-BRIEF": ["superbrief"],
    "TURN": ["turn", "rotate"],
    "PUSH": ["push", "press", "move"],
    "PULL": ["pull"],
    "CLIMB": ["climb", "scale"],
    "SWIM": ["swim"],
    "PRAY": ["pray"],
    "EAT": ["eat"],
    "DRINK": ["drink"],
    "BURN": ["burn", "light"],
    "TIE": ["tie", "attach", "fasten"],
    "WAVE": ["wave"],
    "RING": ["ring"],
    "FILL": ["fill"],
    "POUR": ["pour"],
    "DIG": ["dig"],
    "BOARD": ["board"],
    "DISEMBARK": ["disembark", "unboard"],
    "MUNG": ["mung", "destroy", "break", "smash", "crack"],
    "HELLO": ["hello", "hi"],
    "YELL": ["yell", "shout"],
    "SLEEP": ["sleep"],
    "WAKE-UP": ["wake"],
    "FIND": ["find", "where"],
    "TAKE-OFF": ["take-off", "remove", "doff"],
    # Verb-with-prep-iobj routines: ZIL syntax like ``<SYNTAX PUT
    # OBJECT ON OBJECT = V-PUT-ON>`` means the player types ``put X on
    # Y`` — the parser sees ``put`` as the verb (not ``put_on``).  The
    # per-object handler dispatched from ``<VERB? PUT-ON>`` therefore
    # needs to register under the BARE verb name with ``--ispec
    # <prep>:this`` so dispatch reaches it.  Compound-particle verbs
    # (LIE-DOWN, WALK-AROUND, LOOK-INSIDE) keep their compound names
    # because the parser combines the two-word verb-particle pair into
    # a single token.
    "PUT-ON": ["put"],
    "PUT-IN": ["put"],
    "PUT-UNDER": ["put"],
    "PUT-AT": ["put"],
    "PUT-BEFORE": ["put"],
    "PUT-OVER": ["put"],
    "PUT-AROUND": ["put"],
    "PUT-IN-FRONT": ["put"],
    "GIVE-TO": ["give"],
    # Note: V-X-WITH variants (BLOCK-WITH, FILL-WITH, ATTACK-WITH, etc.)
    # are NOT aliased to the bare verb.  ZIL action handlers that branch
    # on ``<VERB? X-WITH>`` use the routine name to distinguish "X" (no
    # iobj) from "X-WITH" (iobj present), and the translated body's
    # ``the_player_verb == 'x_with'`` check needs the compound name to
    # match the synthetic call from ``_.perform('x_with', ...)``.  Player
    # input ``block panel with satchel`` reaches them via a verb-file
    # alias added separately (todo) or via the substrate fallback.
    "WEAR": ["wear", "don", "put-on"],
    "BRUSH": ["brush", "clean"],
    "LOWER": ["lower"],
    "RAISE": ["raise"],
    "WIND": ["wind"],
    "COUNT": ["count"],
    "SQUEEZE": ["squeeze"],
    "SMELL": ["smell", "sniff"],
    "LISTEN": ["listen", "hear"],
    "TOUCH": ["touch", "feel"],
    "TASTE": ["taste"],
    "KNOCK": ["knock"],
}
