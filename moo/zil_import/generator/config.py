"""
Generator argument bundles.

``generate_all`` historically took a long parameter list of optional
dicts (tables, globals, syntax, synonyms, compound, bare-syntax) plus
a linter and a game-config knob.  ``GeneratorIR`` and
``GeneratorOptions`` group them so callers don't have to thread eight
kwargs every time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..game_config import GameConfig
from ..ir import ZilSyntaxRule


@dataclass
class GeneratorIR:
    """
    Optional intermediate-representation dicts produced by the converter.

    Each is keyed by a ZIL atom; values describe tables, scalar
    globals, SYNTAX rules, SYNONYM aliases, compound-verb particles,
    and bare-form syntax rules.  Absent keys default to empty dicts so
    the generator can run on partial IR.

    :ivar tables: Atom → ZIL table values.
    :ivar globals_dict: Atom → scalar GLOBAL initial value.
    :ivar syntax_dict: Verb → list of ``(arity, V-routine)`` tuples.
    :ivar synonyms_dict: Verb → synonym list.
    :ivar compound_verb_dict: ``(verb, particle)`` → V-routine.
    :ivar bare_syntax_dict: Bare-form syntax rules; ``None`` means
        "use ``syntax_dict``".
    :ivar rules: Verb → typed :class:`ZilSyntaxRule` list.  The
        per-syntax-row emitter consumes this; legacy dispatcher
        emission reads the dict views above.
    """

    tables: dict[str, list] = field(default_factory=dict)
    globals_dict: dict[str, object] = field(default_factory=dict)
    syntax_dict: dict[str, list[tuple[int, str]]] = field(default_factory=dict)
    synonyms_dict: dict[str, list[str]] = field(default_factory=dict)
    compound_verb_dict: dict[tuple[str, str], str] = field(default_factory=dict)
    bare_syntax_dict: dict[str, list[tuple[int, str]]] | None = None
    rules: dict[str, list[ZilSyntaxRule]] = field(default_factory=dict)

    def normalized(self) -> "GeneratorIR":
        """
        Fill in ``bare_syntax_dict`` from ``syntax_dict`` when omitted.

        :returns: A new instance with ``bare_syntax_dict`` populated.
        """
        return GeneratorIR(
            tables=self.tables,
            globals_dict=self.globals_dict,
            syntax_dict=self.syntax_dict,
            synonyms_dict=self.synonyms_dict,
            compound_verb_dict=self.compound_verb_dict,
            bare_syntax_dict=self.bare_syntax_dict if self.bare_syntax_dict is not None else self.syntax_dict,
            rules=self.rules,
        )


@dataclass
class GeneratorOptions:
    """
    Per-run options for ``generate_all``.

    :ivar linter: Optional ``moo.zil_import.lint.Linter``.  When
        set, the generator runs per-file pylint and raises on threshold
        breach.
    :ivar game_config: Per-game knobs (banner, dataset name, NPC atom
        map).  Defaults to ``ZORK1_CONFIG`` when ``None``.
    """

    linter: Optional[object] = None  # Linter | None — avoid hard import
    game_config: Optional[GameConfig] = None
