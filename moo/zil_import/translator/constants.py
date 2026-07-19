"""
Translator-wide constants.

Keyword/builtin shadow sets, ZIL atom-to-property maps, dispatch tables,
and the SDK-head whitelist.  None depend on per-routine state.
"""

from __future__ import annotations


PY_KEYWORDS = frozenset(
    {
        "False",
        "None",
        "True",
        "and",
        "as",
        "assert",
        "async",
        "await",
        "break",
        "class",
        "continue",
        "def",
        "del",
        "elif",
        "else",
        "except",
        "finally",
        "for",
        "from",
        "global",
        "if",
        "import",
        "in",
        "is",
        "lambda",
        "nonlocal",
        "not",
        "or",
        "pass",
        "raise",
        "return",
        "try",
        "while",
        "with",
        "yield",
    }
)

# Builtins a ZIL atom would shadow — sanitize the local, keep the builtin.
PY_BUILTIN_SHADOWS = frozenset(
    {
        "set",
        "list",
        "dict",
        "tuple",
        "str",
        "int",
        "float",
        "bool",
        "type",
        "id",
        "len",
        "min",
        "max",
        "sum",
        "all",
        "any",
        "map",
        "filter",
        "print",
        "open",
        "input",
        "object",
        "next",
        "iter",
        "range",
    }
)

# Django Model methods/attributes that shadow verb names when accessed via
# dot syntax on an Object. ``obj.clean`` returns ``Model.clean`` (validation
# no-op) instead of the verb — the verb fires silently with no output.
# When a verb's snake-name lands here, fall back to ``invoke_verb("name")``.
DJANGO_MODEL_SHADOWS = frozenset(
    {
        "clean",
        "save",
        "delete",
        "full_clean",
        "validate_unique",
        "validate_constraints",
        "refresh_from_db",
        "check",
        "pk",
        "serializable_value",
        "prepare_database_save",
        "get_deferred_fields",
        "adelete",
        "asave",
        "arefresh_from_db",
    }
)


# Pylint disables on generated verbs — see explanation/zil-importer (Pylint disables on generated verbs).
# Three categories that pylint structurally cannot resolve:
#   * return-outside-function — verb bodies aren't inside a Python function.
#   * undefined-variable — framework injects context, lookup, _, wizard, verb_name.
#   * no-name-in-module — moo.sdk is reached via a PEP 420 namespace package
#     contributed by both django-moo and moo-agent; static analysis can't see it.
# Any other category that fires is treated as a translator-polish opportunity,
# not a noise source to silence.
DISABLE_INTRINSIC = "return-outside-function,undefined-variable,no-name-in-module"
DISABLE_FULL = DISABLE_INTRINSIC


# P?<dir> atoms — see explanation/zil-importer (Direction-token (`P?`) atoms).
DIRECTION_ATOMS: dict[str, str] = {
    "P?LAND": "land",
    "P?NORTH": "north",
    "P?SOUTH": "south",
    "P?EAST": "east",
    "P?WEST": "west",
    "P?UP": "up",
    "P?DOWN": "down",
    "P?NE": "ne",
    "P?NW": "nw",
    "P?SE": "se",
    "P?SW": "sw",
    "P?IN": "in",
    "P?OUT": "out",
}


# ZIL property atom → DjangoMOO property name.
PROP_MAP: dict[str, str] = {
    "P?LDESC": "description",
    "P?FDESC": "first_description",
    "P?DESC": "description",
    "P?ACTION": "action",
    "P?CAPACITY": "capacity",
    "P?SIZE": "size",
    "P?VALUE": "value",
    "P?TVALUE": "tvalue",
    "P?TEXT": "text",
    "P?SYNONYM": "synonyms",
    "P?ADJECTIVE": "adjectives",
    "P?FLAGS": "flags",
    "P?GLOBAL": "global_scenery",
    "P?IN": "location",
    "P?LOC": "location",
    "P?DEST": "dest",
    "P?EXIT": "exit_routine",
    "P?NOGO": "nogo_msg",
    "P?DIR": "direction",
    "P?COND": "condition_flag",
    "P?SCORE": "value",
    "P?STRENGTH": "strength",
    "P?WEAPON": "weapon",
    "P?FIGHTS": "fights",
    "P?MELEE": "melee",
    "P?VILLAINS": "villains",
}


# Game-neutral ZIL global atom → Python expression.
# Per-game NPC atoms are merged in by ZilTranslator from GameConfig.npc_atom_map.
GLOBAL_MAP: dict[str, str] = {
    "WINNER": "context.player",
    # See explanation/zil-importer (`,ADVENTURER` resolves to the live player).
    "ADVENTURER": "context.player",
    # PROTAGONIST is HHG's name for the current player (used by V-WEAR's
    # `<MOVE ,PRSO ,PROTAGONIST>` and similar). Resolving it as a static
    # lookup leaves the player carrying things in a phantom "it
    # (PROTAGONIST)" object that no parser scope can see.
    "PROTAGONIST": "context.player",
    "HERE": "context.player.here()",
    # PRSO/PRSI emit a name binding (`prso`/`prsi`) that the polish phase
    # hoists to the routine top via _maybe_hoist_prso/_prsi.  For --dspec
    # this substrate verbs, a None-guard early return is also injected so
    # downstream attribute access doesn't AttributeError on missing dobj.
    "PRSO": "prso",
    "PRSI": "prsi",
    "PRSA": "verb_name",
    "P-PRSO": "prso",
    "P-PRSI": "prsi",
    "SCORE": "context.player.zstate_get('SCORE')",
    "MOVES": "context.player.zstate_get('MOVES')",
    "DEATHS": "context.player.zstate_get('DEATHS')",
    "VERBOSE-MODE": "context.player.zstate_get('VERBOSE-MODE')",
    "SUPERBRIEF": "context.player.zstate_get('SUPERBRIEF')",
    "ROOMS": "context.player.zstate_get('ROOMS')",
    # Parser-state globals: P-CONT (current-word pointer) and P-LEN
    # (word count) advance through the lex buffer in ZIL. The closest
    # safe mapping for both is `len(context.parser.words)` — that way
    # `<GET ,P-LEXV ,P-CONT>` translates to a `parser.words[len-1]`
    # form that resolves to the last input word, which is what
    # V-ANSWER's W?YES / W?NO check actually wants. Reads only — SETG
    # of these atoms is handled separately by the SETG translator.
    #
    # V-TELL in HHG uses ``,P-CONT`` as a continuation-test (
    # "did the user say ``tell barman, do X``?"); DjangoMOO doesn't
    # support intra-line continuations so the always-truthy mapping
    # makes V-TELL silently set WINNER instead of firing the canonical
    # "Hmmm... <actor> looks at you expectantly" branch.  A hand-written
    # ``verbs/thing/substrate_verbs/tell.py`` override addresses
    # that without breaking the index use case here.
    "P-CONT": "len(context.parser.words) if context.parser is not None else 0",
    "P-LEN": "len(context.parser.words) if context.parser is not None else 0",
    "P-LEXV": "context.parser.words if context.parser is not None else []",
    "PLAYER": "context.player",
    "LIT-ROOM": "context.player.zstate_get('LIT-ROOM')",
    "ENDGAME": "context.player.zstate_get('ENDGAME')",
    "DEAD": "context.player.zstate_get('DEAD')",
    "LUCKY": "context.player.zstate_get('LUCKY')",
    "LAST-SCORE": "context.player.zstate_get('LAST-SCORE')",
}


# ZIL M-* lifecycle hooks fired by APPLY — see explanation/zil-importer (M-* lifecycle hooks).
M_CLAUSES = {"M-LOOK", "M-BEG", "M-END", "M-ENTER", "M-LEAVE", "M-FLASH", "M-OBJDESC"}

# ZIL combat dispatch — see explanation/zil-importer (F-* combat dispatch).
F_CLAUSES = {"F-DEAD", "F-UNCONSCIOUS", "F-CONSCIOUS", "F-BUSY?", "F-FIRST?"}


# M-* / F-* constant → DjangoMOO verb name; drives per-clause filename splits.
M_TO_VERB: dict[str, str] = {
    "M-LOOK": "look",
    "M-BEG": "preturnfunc",
    "M-END": "turnfunc",
    "M-ENTER": "enterfunc",
    "M-LEAVE": "exitfunc",
    "M-FLASH": "flashfunc",
    "M-OBJDESC": "descfunc",
    "F-BUSY?": "f_busy_p",
    "F-DEAD": "f_dead",
    "F-UNCONSCIOUS": "f_unconscious",
    "F-CONSCIOUS": "f_conscious",
    "F-FIRST?": "f_first_p",
}


# ZIL form heads recognised as primitives/SDK calls; others are user routines.
SDK_HEADS: set[str] = {
    # control flow / output
    "RTRUE",
    "RFALSE",
    "RETURN",
    "TELL",
    "CRLF",
    "PRINT",
    "PRINT-CR",
    "PRINTR",
    "PRINTN",
    "PRINTB",
    "PRINTC",
    "COND",
    "AND",
    "OR",
    "NOT",
    "REPEAT",
    "PROG",
    "MAP-CONTENTS",
    "SET",
    # movement / state
    "MOVE",
    "REMOVE",
    "REMOVE-CAREFULLY",
    "GOTO",
    "DO-WALK",
    "FSET",
    "FCLEAR",
    "FSET?",
    "PUTP",
    "GETP",
    "SETG",
    "GVAL",
    "IN?",
    "LOC",
    "FIRST?",
    "FIRST",
    "NEXT?",
    "NEXT",
    "GLOBAL-IN?",
    # arithmetic / comparison
    "+",
    "ADD",
    "-",
    "SUB",
    "*",
    "MUL",
    "/",
    "DIV",
    "MOD",
    "ABS",
    "MIN",
    "MAX",
    "==",
    "==?",
    "EQUAL?",
    "=?",
    "N==?",
    "N=?",
    "G?",
    "GRTR?",
    "L?",
    "LESS?",
    "G=?",
    "L=?",
    "0?",
    "ZERO?",
    "1?",
    # game systems
    "SCORE",
    "JIGS-UP",
    "ENABLE",
    "DISABLE",
    "PERFORM",
    "PICK-ONE",
    "VERB?",
    "RANDOM",
    "PROB",
    "OBJECT-PNAME",
    # display / screen-window opcodes
    "SPLIT",
    "SCREEN",
    "CURSET",
    "CURGET",
    "CLEAR",
    "DCLEAR",
    "HLIGHT",
    "COLOR",
    "FONT",
    "BUFOUT",
    "DIROUT",
}
