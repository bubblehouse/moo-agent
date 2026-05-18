"""
ZIL routine AST → DjangoMOO Python verb body.

See :doc:`/reference/zil-importer` for the public API and translation
idioms; :doc:`/explanation/zil-importer` for the why.
"""

from __future__ import annotations

import re
import textwrap
from typing import Any

from ..game_config import ZORK1_CONFIG, GameConfig
from ..ir import FLAG_PROPERTIES, ZIL_VERBS, ZilRoutine
from ..parser import Str
from .constants import (
    DISABLE_FULL,
    DISABLE_INTRINSIC,
    F_CLAUSES,
    M_CLAUSES,
    DIRECTION_ATOMS,
    GLOBAL_MAP,
    M_TO_VERB,
    PROP_MAP,
    PY_BUILTIN_SHADOWS,
    PY_KEYWORDS,
    SDK_HEADS,
)
from .identifiers import (
    as_object,
    ends_in_unconditional_return,
    predicate_python_name,
    pylint_disable_line,
    routine_dot_name,
    sanitize_ident,
    substrate_receiver,
    verb_attr_safe,
)

# Re-exports keep `from extras.zil_import.translator import …` working unchanged.
__all__ = [
    "DIRECTION_ATOMS",
    "DISABLE_FULL",
    "DISABLE_INTRINSIC",
    "FLAG_PROPERTIES",
    "F_CLAUSES",
    "GLOBAL_MAP",
    "GameConfig",
    "M_CLAUSES",
    "M_TO_VERB",
    "PROP_MAP",
    "PY_BUILTIN_SHADOWS",
    "PY_KEYWORDS",
    "SDK_HEADS",
    "Str",
    "ZIL_VERBS",
    "ZORK1_CONFIG",
    "ZilRoutine",
    "ZilTranslator",
    "as_object",
    "ends_in_unconditional_return",
    "has_f_dispatch",
    "has_m_dispatch",
    "predicate_python_name",
    "pylint_disable_line",
    "routine_dot_name",
    "sanitize_ident",
    "translate_f_clause",
    "translate_m_clause",
    "translate_routine",
    "verb_attr_safe",
]


class ZilTranslator:
    """
    Translate a single ZilRoutine body into Python verb source.

    See :doc:`/reference/zil-importer` (ZilTranslator state) for the
    full meaning of each constructor argument.

    :param routine: ZIL routine IR to translate.
    :param object_atoms: Atoms naming a Room/Object — drive
        ``lookup("name")`` emission for atom refs.
    :param routine_atoms: Atoms naming another ZIL routine — drive
        zero-arg dispatch on bare atoms in expression position.
    :param action_owner: ``(atom, is_room)`` of the owning room/object,
        or ``None`` for global helpers.
    :param owner_overrides: Per-routine ``--on $<owner>`` shebang
        overrides (uppercase routine name → owner property).
    :param pre_handler_routines: V-routine names whose ``PRE-X``
        handler should be inlined at the top of the substrate body.
    :param display_names: Atom → globally-unique display name.
    :param substrate_display_names: Substrate snake-name → display name.
    :param routine_to_verbs: V-routine name → list of player verbs that
        dispatch to it via SYNTAX rules.
    :param strictly_zero_object: V-routine names whose only SYNTAX form
        is 0-OBJECT (emit no ``--dspec``).
    :param lint_active: When set, emit only format-intrinsic pylint
        disables in the verb-file header.
    :param game_config: Per-game configuration; defaults to ``ZORK1_CONFIG``.
    """

    def __init__(
        self,
        routine: ZilRoutine,
        object_atoms: set[str] | None = None,
        routine_atoms: set[str] | None = None,
        action_owner: tuple[str, bool] | None = None,
        owner_overrides: dict[str, str] | None = None,
        pre_handler_routines: set[str] | None = None,
        display_names: dict[str, str] | None = None,
        substrate_display_names: dict[str, str] | None = None,
        routine_to_verbs: dict[str, list[str]] | None = None,
        strictly_zero_object: set[str] | None = None,
        lint_active: bool = False,
        game_config: GameConfig | None = None,
    ) -> None:
        self.routine = routine
        self.object_atoms = {a.upper() for a in (object_atoms or set())}
        self.routine_atoms = {a.upper() for a in (routine_atoms or set())}
        self.action_owner = action_owner
        self.owner_overrides: dict[str, str] = owner_overrides or {}
        self.pre_handler_routines: set[str] = pre_handler_routines or set()
        self.display_names: dict[str, str] = display_names or {}
        self.substrate_display_names: dict[str, str] = substrate_display_names or {}
        self.routine_to_verbs: dict[str, list[str]] = routine_to_verbs or {}
        self.strictly_zero_object: set[str] = strictly_zero_object or set()
        self._indent = 0
        self._lines: list[str] = []
        self._imports: set[str] = set()
        # Verbs collected from <VERB? FOO BAR> forms; consumed by _shebang().
        self._verbs_handled: set[str] = set()
        # Pre-set by the generator: per-clause splits already emitted.
        self._clause_split_verbs: set[str] = set()
        # See explanation/zil-importer (REPEAT loop semantics).
        self._repeat_depth = 0
        # See explanation/zil-importer (M-clause player-verb binding).
        self._in_m_clause = False
        self.lint_active = lint_active
        self.game_config = game_config or ZORK1_CONFIG
        self._global_map = dict(GLOBAL_MAP)
        for atom, target in self.game_config.npc_atom_map.items():
            self._global_map[atom.upper()] = f'lookup("{target}")'

    def _is_noop_body(self, forms: list) -> bool:
        """
        Return True when an M-clause body is effectively a no-op.

        Detects bare ``<>`` / ``RTRUE`` / ``RFALSE``.  Emitting an empty
        verb on the object would override the substrate via
        last-match-wins, so the generator skips emission instead.

        :param forms: Body forms to inspect.
        :returns: ``True`` when the body has no semantic content.
        """
        if not isinstance(forms, list):
            return forms is None
        if not forms:
            return True
        if len(forms) > 1:
            return False
        only = forms[0]
        if only is None:
            return True
        if isinstance(only, str):
            upper = only.upper()
            return upper in ("RTRUE", "RFALSE", "T", "<>", "FALSE")
        if isinstance(only, list) and only:
            head = only[0]
            if isinstance(head, str) and head.upper() in ("RTRUE", "RFALSE", "RETURN"):
                return True
        return False

    def _ends_with_rfalse(self, forms: list) -> bool:
        """
        Return True when the clause body ends with an explicit ``<RFALSE>``.

        Per-turn bookkeeping handlers like NO-OBJS use a trailing RFALSE
        to declare "I'm a passive observer — let normal verb dispatch
        proceed."  Callers use this to skip the ``return True`` injection
        that's appropriate for handlers that print a response and want
        to suppress the verb.

        :param forms: Body forms to inspect.
        :returns: ``True`` when the last form is ``RFALSE``.
        """
        if not isinstance(forms, list) or not forms:
            return False
        last = forms[-1]
        if isinstance(last, str) and last.upper() == "RFALSE":
            return True
        if isinstance(last, list) and last:
            head = last[0]
            if isinstance(head, str) and head.upper() == "RFALSE":
                return True
        return False

    def _is_prso_atom(self, node) -> bool:
        """
        True if ``node`` is a ZIL ``,PRSO`` reference.

        :param node: AST node to test.
        :returns: ``True`` for any ``,PRSO`` / ``.PRSO`` form.
        """
        return isinstance(node, str) and node.lstrip(",.").upper() == "PRSO"

    def _direction_string(self, node) -> str | None:
        """
        Return the direction string for a ``,P?<DIR>`` ref, or ``None``.

        :param node: AST node to test.
        :returns: The direction (e.g. ``"east"``) for a ``,P?EAST``
            reference; ``None`` otherwise.
        """
        if isinstance(node, str):
            atom = node.lstrip(",.").upper()
            return DIRECTION_ATOMS.get(atom)
        return None

    def _is_clause_test(self, test, dispatch_var: str, allowed: set[str]) -> bool:
        """
        Generic detector for ``<EQUAL? .<dispatch_var> ,<CONST> ...>``.

        :param test: The COND clause's test form.
        :param dispatch_var: The local-var name being compared (e.g. ``RARG``).
        :param allowed: The set of constants the test may compare against.
        :returns: ``True`` when ``test`` matches the dispatch shape.
        """
        if not isinstance(test, list) or len(test) < 3:
            return False
        head = test[0]
        if not isinstance(head, str) or head.upper() not in ("EQUAL?", "==?", "=?", "=="):
            return False
        arg1 = test[1]
        if not isinstance(arg1, str) or arg1.lstrip(",.").upper() != dispatch_var:
            return False
        for arg in test[2:]:
            if not isinstance(arg, str):
                return False
            if arg.lstrip(",.").upper() not in allowed:
                return False
        return True

    def _is_m_clause_test(self, test) -> bool:
        """
        True if test is ``<EQUAL? .RARG ,M-X ...>`` (lifecycle-event clause).

        :param test: The COND clause's test form.
        :returns: ``True`` for an M-* lifecycle-dispatch test.
        """
        return self._is_clause_test(test, "RARG", M_CLAUSES)

    def _is_f_clause_test(self, test) -> bool:
        """
        True if test is ``<EQUAL? .MODE ,F-X ...>`` (combat-state clause).

        :param test: The COND clause's test form.
        :returns: ``True`` for an F-* combat-dispatch test.
        """
        return self._is_clause_test(test, "MODE", F_CLAUSES)

    def _is_verb_clause_test(self, test) -> bool:
        """
        Return True if a COND clause test is dispatched on player verb.

        Recognises ``<VERB? X Y>`` and ``<AND <VERB? X> ...other...>``.
        These clauses are split out into per-clause verb files so the parser
        does natural dispatch instead of an ``if player_verb in [...]``
        switch inside one god-verb.

        :param test: The COND clause's test form.
        :returns: ``True`` for any ``<VERB?>`` dispatch test.
        """
        if not isinstance(test, list) or not test:
            return False
        head = test[0]
        if not isinstance(head, str):
            return False
        upper = head.upper()
        if upper == "VERB?":
            return True
        if upper == "AND":
            for sub in test[1:]:
                if isinstance(sub, list) and sub and isinstance(sub[0], str) and sub[0].upper() == "VERB?":
                    return True
        return False

    def _verbs_in_test(self, test) -> list[str]:
        """
        Extract verb atoms from a ``<VERB? X Y>`` or ``<AND <VERB? X> ...>``.

        :param test: The COND clause's test form.
        :returns: List of verb atoms (upper-case), or ``[]`` for non-VERB? tests.
        """
        if not isinstance(test, list) or not test:
            return []
        head = str(test[0]).upper()
        if head == "VERB?":
            return [str(v).upper() for v in test[1:] if isinstance(v, str)]
        if head == "AND":
            for sub in test[1:]:
                if isinstance(sub, list) and sub and isinstance(sub[0], str) and sub[0].upper() == "VERB?":
                    return [str(v).upper() for v in sub[1:] if isinstance(v, str)]
        return []

    def _extra_test_in_and(self, test) -> list | None:
        """
        For ``<AND <VERB? X> <other>>`` return ``<AND <other> ...>``.

        :param test: The COND clause's test form.
        :returns: The non-VERB? remainder, or ``None`` if there is none.
        """
        if not isinstance(test, list) or not test or str(test[0]).upper() != "AND":
            return None
        extras = [
            sub
            for sub in test[1:]
            if not (isinstance(sub, list) and sub and isinstance(sub[0], str) and sub[0].upper() == "VERB?")
        ]
        if not extras:
            return None
        if len(extras) == 1:
            return extras[0]
        return ["AND", *extras]

    def _prune_clauses_in_forms(self, forms: list, predicate) -> list:
        """
        Generic pruner: drop COND clauses whose test matches ``predicate``.

        :param forms: Body forms to walk.
        :param predicate: Callable invoked on each COND clause's test.
        :returns: The forms with matching clauses removed.
        """
        if not isinstance(forms, list):
            return forms
        result = []
        for form in forms:
            if isinstance(form, list) and form and isinstance(form[0], str) and form[0].upper() == "COND":
                head = form[0]
                kept = [head]
                any_dropped = False
                for clause in form[1:]:
                    if not isinstance(clause, (list, tuple)) or not clause:
                        kept.append(clause)
                        continue
                    if predicate(clause[0]):
                        any_dropped = True
                        continue
                    kept.append(clause)
                if any_dropped and len(kept) == 1:
                    continue
                result.append(kept)
            else:
                result.append(form)
        return result

    def _prune_m_clauses_in_forms(self, forms: list) -> list:
        """
        Remove M-* lifecycle clauses from any top-level COND.

        After ``translate_m_clause`` emits the M-* branches as separate
        verb files, the residual full-routine body drops them.

        :param forms: Body forms to walk.
        :returns: The forms with M-* clauses removed.
        """
        return self._prune_clauses_in_forms(forms, self._is_m_clause_test)

    def _prune_f_clauses_in_forms(self, forms: list) -> list:
        """
        Remove F-* combat clauses from any top-level COND in ``forms``.

        :param forms: Body forms to walk.
        :returns: The forms with F-* clauses removed.
        """
        return self._prune_clauses_in_forms(forms, self._is_f_clause_test)

    def _find_verb_dispatch(self, forms: list) -> list | None:
        """
        Find a top-level COND that has at least one VERB? clause.

        :param forms: Body forms to walk.
        :returns: The matching COND form, or ``None``.
        """
        for form in forms:
            if not isinstance(form, list) or not form:
                continue
            if str(form[0]).upper() != "COND":
                continue
            for clause in form[1:]:
                if not isinstance(clause, (list, tuple)) or not clause:
                    continue
                if self._is_verb_clause_test(clause[0]):
                    return form
        return None

    def _verb_clauses(self, forms: list) -> list[tuple[list[str], list, list]]:
        """
        Yield ``(verb_atoms, extra_test, body_forms)`` for each VERB? clause.

        :param forms: Body forms to walk.
        :returns: A list of ``(verb_atoms, extra_test, body_forms)`` tuples.
        """
        dispatch = self._find_verb_dispatch(forms)
        if dispatch is None:
            return []
        out: list[tuple[list[str], list, list]] = []
        for clause in dispatch[1:]:
            if not isinstance(clause, (list, tuple)) or not clause:
                continue
            test = clause[0]
            if not self._is_verb_clause_test(test):
                continue
            verbs = self._verbs_in_test(test)
            if not verbs:
                continue
            extra = self._extra_test_in_and(test)
            body = list(clause[1:])
            out.append((verbs, extra, body))
        return out

    def _prune_verb_clauses_in_forms(self, forms: list) -> list:
        """
        Remove VERB?-tested clauses from any top-level COND.

        Preserves T/ELSE defaults; unwraps a sole T/ELSE clause to its
        body so the residual emits the body directly instead of an
        awkward ``if True: ...`` wrapper.

        :param forms: Body forms to walk.
        :returns: The forms with VERB?-tested clauses removed.
        """
        if not isinstance(forms, list):
            return forms
        result = []
        for form in forms:
            if isinstance(form, list) and form and isinstance(form[0], str) and form[0].upper() == "COND":
                head = form[0]
                kept = [head]
                any_dropped = False
                for clause in form[1:]:
                    if not isinstance(clause, (list, tuple)) or not clause:
                        kept.append(clause)
                        continue
                    if self._is_verb_clause_test(clause[0]):
                        any_dropped = True
                        continue
                    kept.append(clause)
                if any_dropped and len(kept) == 1:
                    continue
                # Sole T/ELSE clause → inline its body forms (drop the COND wrapper).
                if any_dropped and len(kept) == 2:
                    only_clause = kept[1]
                    if isinstance(only_clause, (list, tuple)) and only_clause:
                        test = only_clause[0]
                        if isinstance(test, str) and test.upper() in ("T", "ELSE"):
                            result.extend(list(only_clause[1:]))
                            continue
                result.append(kept)
            else:
                result.append(form)
        return result

    def translate(self) -> str:
        """
        Return the full verb-file body, or empty when the residual is a no-op.

        M-/F-/VERB? clauses that get split into per-clause files are
        pruned here so the residual god-verb carries only the catch-all
        body.

        :returns: The complete verb-file source, or ``""`` when the
            generator should skip emission.
        """
        body_forms = self.routine.body
        any_pruned = False
        if self.has_m_dispatch():
            body_forms = self._prune_m_clauses_in_forms(body_forms)
            any_pruned = True
        if self.has_f_dispatch():
            body_forms = self._prune_f_clauses_in_forms(body_forms)
            any_pruned = True
        if self.action_owner and self._find_verb_dispatch(body_forms) is not None:
            body_forms = self._prune_verb_clauses_in_forms(body_forms)
            any_pruned = True
        if any_pruned and self._is_noop_body(body_forms):
            return ""
        # Reset _verbs_handled so the residual shebang only carries verbs still referenced.
        self._verbs_handled = set()
        body_lines = self._translate_body(body_forms)

        # Skip emission when pruning leaves no semantic content (only
        # comments/`pass`).  Bare `# ZIL: …` unhandled-form fallbacks are
        # legitimate, so we only short-circuit when something was pruned.
        def _is_semantically_empty(lines: list[str]) -> bool:
            for line in lines:
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or stripped == "pass":
                    continue
                return False
            return True

        if any_pruned and _is_semantically_empty(body_lines):
            return ""
        # Make ZIL's implicit-return-of-last-expression explicit.
        body_lines = self._wrap_trailing_return_recursive(body_lines, 0)
        # Per-action-owner residuals (the "leftovers" after VERB? clauses are
        # split into separate files) also need a ``passthrough()`` at the end
        # so unhandled fall-off invokes the substrate verb on the parent class.
        # Without this, an action_owner verb like trap_door's residual that
        # only handles the CELLAR branch falls off silently in LIVING-ROOM
        # — masking the per-clause Living-Room split because the residual's
        # PK is lower (loaded first → wins same-rank tie in parser dispatch).
        # Skip the append when the body already ends in an unconditional
        # ``return`` at indent 0 — otherwise pylint flags the trailing
        if self.action_owner and any_pruned and not ends_in_unconditional_return(body_lines):
            body_lines.append("return passthrough()")
        # See explanation/zil-importer (`pre-X` substrate inlining).
        if self.routine.name.upper() in self.pre_handler_routines:
            base = self.routine.name.lower().removeprefix("v-")
            pre_lines = [
                f'pre_x = "pre_{base}"',
                "if _.zork_thing.invoke_verb(pre_x):",
                "    return",
            ]
            body_lines = pre_lines + body_lines
        # Build param/aux unpacks first so auto-import scans their default exprs too.
        unpack_lines: list[str] = []
        for i, param in enumerate(self.routine.params):
            default = self.routine.initial_values.get(param)
            default_expr = self._translate_expr(default) if default is not None else "None"
            unpack_lines.append(f"{sanitize_ident(param)} = args[{i}] if len(args) > {i} else {default_expr}")
        for aux in self.routine.aux_vars:
            default = self.routine.initial_values.get(aux)
            # See explanation/zil-importer (Aux-local default = 0).
            default_expr = self._translate_expr(default) if default is not None else "0"
            unpack_lines.append(f"{sanitize_ident(aux)} = {default_expr}")
        body_lines, unpack_lines = self._polish(body_lines, unpack_lines)
        # PRE-X routines need ``return True`` on print-and-stop branches so
        # the substrate V-X caller (``if invoke_verb(pre_x): return``) treats
        # them as "handled, don't fall through."  ZIL's implicit RFALSE on
        # the COND tail would otherwise reach V-X and double-print the
        # canonical "Taken." after the pre-handler's refusal message.
        # Run AFTER polish because ``_fix_return_print`` splits
        # ``return print(...)`` into ``print(...); return`` — the bare
        # returns we promote only exist after that split.
        if self.routine.name.upper().startswith("PRE-"):
            body_lines = self._bare_return_to_return_true(body_lines)
        # Bind `the_player_verb` from the parser when the residual has a <VERB?> check.
        # See explanation/zil-importer (M-clause player-verb binding) for the M-clause path.
        if self._verbs_handled:
            unpack_lines.append("the_player_verb = invoked_verb_name(verb_name)")
        # --dspec this substrate verbs need a missing-dobj guard so attribute
        # access on `prso` doesn't AttributeError when the user types e.g.
        # bare `put`.  See explanation/zil-importer (PRSO / PRSI no-raise guard).
        body_lines = self._maybe_inject_prso_guard(body_lines, unpack_lines)
        self._auto_import(unpack_lines + body_lines)
        imports = self._build_imports()
        header = self._shebang()
        # Skip emission when per-clause splits cover every verb the residual would register.
        if self.action_owner and self._verbs_handled and not (self._verbs_handled - self._clause_split_verbs):
            return ""
        parts = [
            header,
            "",
            "# Generated by extras/zil_import — do not edit by hand",
            pylint_disable_line(lint_active=self.lint_active),
            "",
        ]
        if imports:
            parts.append(imports)
            parts.append("")
        parts.append(f"# ZIL routine: {self.routine.name}")
        if self.routine.params:
            parts.append(f"# params: {', '.join(self.routine.params)}")
        if self.routine.aux_vars:
            parts.append(f"# aux: {', '.join(self.routine.aux_vars)}")
        parts.append("")
        parts.extend(unpack_lines)
        if unpack_lines:
            parts.append("")
        parts.extend(body_lines)
        return "\n".join(parts) + "\n"

    def translate_f_clause(self, f_constant: str) -> str:
        """
        Translate one F-* combat branch into a verb-file body.

        Mirrors ``translate_m_clause`` but keyed on ``.MODE`` /
        ``F-...``; the emitted file's verb is taken from ``M_TO_VERB``
        (``F-DEAD`` → ``f_dead``) and dispatches on the routine's
        ``action_owner`` (the villain).

        :param f_constant: The F-* constant whose clause to extract
            (e.g. ``"F-DEAD"``).
        :returns: The clause body as a complete verb-file source, or
            ``""`` when the body is a no-op.
        """
        clause_body = self._extract_f_clause(self.routine.body, f_constant)
        if clause_body is None:
            return f"# No {f_constant} clause found in {self.routine.name}\npass\n"
        if self._is_noop_body(clause_body):
            return ""
        body_lines = self._translate_body(clause_body)
        unpack_lines: list[str] = []
        for i, param in enumerate(self.routine.params):
            default = self.routine.initial_values.get(param)
            if default is not None:
                default_expr = self._translate_expr(default)
            else:
                default_expr = f'"{f_constant}"'
            unpack_lines.append(f"{sanitize_ident(param)} = args[{i}] if len(args) > {i} else {default_expr}")
        for aux in self.routine.aux_vars:
            default = self.routine.initial_values.get(aux)
            default_expr = self._translate_expr(default) if default is not None else "0"
            unpack_lines.append(f"{sanitize_ident(aux)} = {default_expr}")
        body_lines, unpack_lines = self._polish(body_lines, unpack_lines)
        self._auto_import(unpack_lines + body_lines)
        imports = self._build_imports()
        header = self._shebang_m(f_constant)
        parts = [
            header,
            "",
            "# Generated by extras/zil_import — do not edit by hand",
            pylint_disable_line(lint_active=self.lint_active),
            "",
        ]
        if imports:
            parts.append(imports)
            parts.append("")
        parts.append(f"# ZIL: {self.routine.name} / {f_constant}")
        parts.append("")
        parts.extend(unpack_lines)
        if unpack_lines:
            parts.append("")
        parts.extend(body_lines)
        return "\n".join(parts) + "\n"

    _BARE_RETURN_RE = re.compile(r"^(\s*)return\s*$")

    def _bare_return_to_return_true(self, body_lines: list[str]) -> list[str]:
        """
        Promote bare ``return`` to ``return True`` for PRE-X handlers.

        ZIL ``<TELL "msg" CR>`` at a COND branch tail becomes
        ``print("msg")`` + a bare ``return`` (ZIL's implicit RFALSE).
        Our substrate calling convention treats truthy returns as
        "handled, suppress fall-through" and bare/falsy returns as
        "fall through to V-X" — so an implicit RFALSE after a print
        wrongly lets the canonical V-X verb fire and double-print.

        Preserves explicit ``return False`` / ``return True`` /
        ``return <expr>`` — only bare ``return`` is rewritten.

        :param body_lines: Generated body lines.
        :returns: Body with bare returns promoted to ``return True``.
        """
        out: list[str] = []
        for line in body_lines:
            m = self._BARE_RETURN_RE.match(line)
            if m:
                out.append(f"{m.group(1)}return True")
            else:
                out.append(line)
        return out

    def _inject_return_true_into_branches(self, body_lines: list[str]) -> list[str]:
        """
        Append ``return True`` to each top-level if/elif/else body.

        Lets M-BEG/M-END handlers signal "handled" to ``do_command``.
        Branches that already end in an unconditional ``return`` are
        left alone (no unreachable code).

        :param body_lines: Generated body lines to rewrite.
        :returns: The body lines with ``return True`` appended to
            qualifying branches.
        """
        if not body_lines:
            return body_lines

        def is_top_branch(line: str) -> bool:
            stripped = line.lstrip()
            return line == stripped and (
                stripped.startswith("if ")
                or stripped.startswith("elif ")
                or stripped.startswith("else:")
                or stripped.startswith("if False:")
                or stripped.startswith("if True:")
            )

        out: list[str] = []
        i = 0
        n = len(body_lines)
        while i < n:
            line = body_lines[i]
            out.append(line)
            if not is_top_branch(line):
                i += 1
                continue
            # Collect this branch's body (lines indented past column 0) until
            # we hit another top-level line or end of input.
            j = i + 1
            body_start = len(out)
            while j < n and (body_lines[j] == "" or body_lines[j].startswith((" ", "\t"))):
                out.append(body_lines[j])
                j += 1
            # Skip empty / pass-only / unconditional-return-tail bodies.
            non_empty = [ln for ln in out[body_start:] if ln.strip() and ln.strip() != "pass"]
            if non_empty and non_empty[-1].strip() != "return True" and not non_empty[-1].strip().startswith("return"):
                indent = len(non_empty[-1]) - len(non_empty[-1].lstrip())
                out.append(" " * indent + "return True")
            i = j
        return out

    def translate_m_clause(self, m_constant: str) -> str:
        """
        Translate one M-* branch into a verb-file body.

        :param m_constant: The M-* constant whose clause to extract
            (e.g. ``"M-BEG"``).
        :returns: The clause body as a complete verb-file source, or
            ``""`` when the clause is a no-op (``<>`` / RFALSE / RTRUE)
            so the substrate verb runs via normal parser dispatch.
        """
        clause_body = self._extract_m_clause(self.routine.body, m_constant)
        if clause_body is None:
            return f"# No {m_constant} clause found in {self.routine.name}\npass\n"
        if self._is_noop_body(clause_body):
            return ""
        # See explanation/zil-importer (M-clause player-verb binding).
        self._in_m_clause = True
        try:
            body_lines = self._translate_body(clause_body)
        finally:
            self._in_m_clause = False
        # M-LOOK substrate skipped V-LOOK's DESCRIBE-OBJECTS — replay it explicitly.
        # Skip the append when the body already ends in describe_objects so
        # rooms whose canonical M-LOOK already calls DESCRIBE-OBJECTS (loud_room,
        # kitchen, etc.) don't double-print room contents.
        if m_constant.upper() == "M-LOOK":
            # Prepend the room-name banner.  Substrate V-LOOK prints the room
            # name before invoking the room's custom M-LOOK (via DESCRIBE-ROOM's
            # ``<TELL D ,HERE CR>`` when location==ROOMS).  When the room has
            # a custom ``look`` verb, parser dispatch bypasses V-LOOK and
            # invokes the per-room ``look.py`` directly, so the banner never
            # gets printed.  Emit it ourselves so rooms with overridden
            # M-LOOK present consistently with substrate-driven rooms.
            body_lines = ["print(this.desc())"] + body_lines
            if not any("describe_objects" in line for line in body_lines[-3:]):
                body_lines = body_lines + ["_.zork_thing.describe_objects(True)"]
        # M-BEG only: signal "handled" via return True so substrate V-X
        # doesn't double-print after the canonical M-BEG response.  M-END
        # routinely RFALSEs (LIVING-ROOM-FCN trophy-case path), so don't
        # inject there.  Skip injection when the ZIL clause body ends in
        # an explicit <RFALSE> (e.g. NO-OBJS) — that's the canonical
        # "passive observer, don't suppress the verb" marker.
        if m_constant.upper() == "M-BEG" and not self._ends_with_rfalse(clause_body):
            body_lines = self._inject_return_true_into_branches(body_lines)
        # Build param/aux unpacks first so auto-import sees default exprs.
        unpack_lines: list[str] = []
        for i, param in enumerate(self.routine.params):
            default = self.routine.initial_values.get(param)
            if default is not None:
                default_expr = self._translate_expr(default)
            else:
                default_expr = f'"{m_constant}"'
            unpack_lines.append(f"{sanitize_ident(param)} = args[{i}] if len(args) > {i} else {default_expr}")
        for aux in self.routine.aux_vars:
            default = self.routine.initial_values.get(aux)
            # See explanation/zil-importer (Aux-local default = 0).
            default_expr = self._translate_expr(default) if default is not None else "0"
            unpack_lines.append(f"{sanitize_ident(aux)} = {default_expr}")
        # `the_player_verb` from args[1] (do_command path); fall back to the
        # SDK helper for direct invokes (e.g. parse.py's post-dispatch
        # turnfunc call for M-END).
        unpack_lines.append("the_player_verb = args[1] if len(args) > 1 else invoked_verb_name(verb_name)")
        body_lines, unpack_lines = self._polish(body_lines, unpack_lines)
        self._auto_import(unpack_lines + body_lines)
        imports = self._build_imports()
        header = self._shebang_m(m_constant)
        parts = [
            header,
            "",
            "# Generated by extras/zil_import — do not edit by hand",
            pylint_disable_line(lint_active=self.lint_active),
            "",
        ]
        if imports:
            parts.append(imports)
            parts.append("")
        parts.append(f"# ZIL: {self.routine.name} / {m_constant}")
        parts.append("")
        parts.extend(unpack_lines)
        if unpack_lines:
            parts.append("")
        parts.extend(body_lines)
        return "\n".join(parts) + "\n"

    def has_m_dispatch(self) -> bool:
        """
        Return True if this routine dispatches on M-* constants via COND/RARG.

        :returns: ``True`` when an M-* dispatch COND is present.
        """
        return self._find_m_dispatch(self.routine.body) is not None

    def has_f_dispatch(self) -> bool:
        """
        Return True if this routine dispatches on F-* constants via COND/MODE.

        :returns: ``True`` when an F-* dispatch COND is present.
        """
        return self._find_f_dispatch(self.routine.body) is not None

    def _constants_in_dispatch(self, dispatch: list, allowed: set[str]) -> list[str]:
        """
        Collect every constant from ``allowed`` that appears in ``dispatch``.

        :param dispatch: A top-level COND form.
        :param allowed: The constant set to extract (M_CLAUSES / F_CLAUSES).
        :returns: List of matched constants, in clause order.
        """
        constants: list[str] = []
        for clause in dispatch[1:]:
            if not isinstance(clause, (list, tuple)) or not clause:
                continue
            cond = clause[0] if isinstance(clause, (list, tuple)) else None
            if isinstance(cond, (list, tuple)) and len(cond) >= 2:
                for item in cond:
                    if isinstance(item, str) and item in allowed:
                        constants.append(item)
            elif isinstance(cond, str) and cond in allowed:
                constants.append(cond)
        return constants

    def m_constants_found(self) -> list[str]:
        """
        Return the list of M-* constants handled by this routine.

        :returns: M-* constants in clause order, or ``[]``.
        """
        dispatch = self._find_m_dispatch(self.routine.body)
        if dispatch is None:
            return []
        return self._constants_in_dispatch(dispatch, M_CLAUSES)

    def f_constants_found(self) -> list[str]:
        """
        Return the list of F-* constants handled by this routine.

        :returns: F-* constants in clause order, or ``[]``.
        """
        dispatch = self._find_f_dispatch(self.routine.body)
        if dispatch is None:
            return []
        return self._constants_in_dispatch(dispatch, F_CLAUSES)

    def has_verb_dispatch(self) -> bool:
        """
        True if the routine has a per-clause-splittable VERB? COND.

        Only action-owner routines get split; global helpers don't.

        :returns: ``True`` when the routine is splittable.
        """
        if not self.action_owner:
            return False
        return self._find_verb_dispatch(self.routine.body) is not None

    def verb_clauses_for_split(self) -> list[tuple[list[str], list, list]]:
        """
        Yield ``(verb_atoms, extra_test, body_forms)`` for each splittable clause.

        :returns: A list of clause tuples.
        """
        return self._verb_clauses(self.routine.body)

    def translate_verb_clause(self, verb_atoms: list[str], extra_test, body_forms: list) -> str:
        """
        Translate one VERB? clause as a complete verb file body.

        :param verb_atoms: ZIL verb atoms the clause dispatches on.
        :param extra_test: Optional extra test from an enclosing AND, or ``None``.
        :param body_forms: Body forms of the clause.
        :returns: Verb-file source, or ``""`` for a no-op body.
        """
        if self._is_noop_body(body_forms):
            return ""
        # Seed _verbs_handled so a bare <RFALSE> at the end of the clause
        # emits passthrough() instead of return False (which would skip
        # the substrate V-routine).
        for atom in verb_atoms:
            self._verbs_handled.add(atom.lower())
        # Strip a trailing <>/RFALSE — it signals "fall through" and the
        # action-owner branch below appends passthrough() exactly once.
        tail_is_rfalse = False
        if body_forms:
            last = body_forms[-1]
            if last is None:
                tail_is_rfalse = True
                body_forms = body_forms[:-1]
            elif isinstance(last, str) and last.upper() in ("<>", "FALSE", "RFALSE"):
                tail_is_rfalse = True
                body_forms = body_forms[:-1]
        # Emit the clause body, optionally wrapped in ``if <extra_test>:``
        # when the original ZIL clause was ``<AND <VERB? X> <other>>``.
        if extra_test is not None:
            wrapped_cond = ["COND", [extra_test, *body_forms]]
            body_lines = self._translate_body([wrapped_cond])
        else:
            body_lines = self._translate_body(body_forms)
        if not tail_is_rfalse:
            body_lines = self._wrap_trailing_return_recursive(body_lines, 0)
        # ZIL action handlers fall through to the V-routine when they end
        # ZIL fall-through: action handlers without an explicit return go
        # to the substrate via passthrough().  Skipped when body already
        # ends in an unconditional return (avoids W0101 unreachable-code).
        if self.action_owner and not ends_in_unconditional_return(body_lines):
            body_lines.append("return passthrough()")

        unpack_lines: list[str] = []
        for i, param in enumerate(self.routine.params):
            default = self.routine.initial_values.get(param)
            default_expr = self._translate_expr(default) if default is not None else "None"
            unpack_lines.append(f"{sanitize_ident(param)} = args[{i}] if len(args) > {i} else {default_expr}")
        for aux in self.routine.aux_vars:
            default = self.routine.initial_values.get(aux)
            # See explanation/zil-importer (Aux-local default = 0).
            default_expr = self._translate_expr(default) if default is not None else "0"
            unpack_lines.append(f"{sanitize_ident(aux)} = {default_expr}")

        body_lines, unpack_lines = self._polish(body_lines, unpack_lines)
        # Bind the_player_verb if any nested <VERB?> survived the split.
        if self._verbs_handled:
            unpack_lines.append("the_player_verb = invoked_verb_name(verb_name)")
        self._auto_import(unpack_lines + body_lines)
        imports = self._build_imports()
        header = self._shebang_verb(verb_atoms)
        parts = [
            header,
            "",
            "# Generated by extras/zil_import — do not edit by hand",
            pylint_disable_line(lint_active=self.lint_active),
            "",
        ]
        if imports:
            parts.append(imports)
            parts.append("")
        verb_label = "/".join(v.lower() for v in verb_atoms)
        parts.append(f"# ZIL routine: {self.routine.name} ({verb_label} branch)")
        parts.append("")
        parts.extend(unpack_lines)
        if unpack_lines:
            parts.append("")
        parts.extend(body_lines)
        return "\n".join(parts) + "\n"

    # ZIL game-initialization routine names that collide with DjangoMOO verbs.
    _SHEBANG_NAME_OVERRIDE: dict[str, str] = {
        "go": "go_v",  # collides with movement verb
    }

    def _on_for_substrate(self, owner_key: str) -> str:
        """
        Render a ``--on`` clause for a substrate parent class.

        :param owner_key: Substrate snake-name (e.g. ``"zork_thing"``).
        :returns: An ``--on "<display>"`` or ``--on $<owner>`` clause.
        """
        display = self.substrate_display_names.get(owner_key)
        if display is not None:
            return f'--on "{display}"'
        return f"--on ${owner_key}"

    def _on_for_atom(self, atom: str) -> str:
        """
        Render a ``--on`` clause for a per-object/per-room handler.

        :param atom: ZIL atom of the room or object.
        :returns: An ``--on "<display>"`` or ``--on $<atom>`` clause.
        """
        display = self.display_names.get(atom)
        if display is not None:
            return f'--on "{display}"'
        return f"--on ${atom.lower().replace('-', '_')}"

    def _shebang_verb(self, verb_atoms: list[str]) -> str:
        """
        Shebang for a per-clause verb file.

        Expands ZIL atoms to player synonyms via ``ZIL_VERBS`` (e.g.
        ATTACK → ``attack kill hit fight stab cut slice mung destroy
        break smash crack``).

        :param verb_atoms: ZIL verb atoms the clause dispatches on.
        :returns: A complete ``#!moo verb …`` shebang line.
        """
        aliases: list[str] = []
        seen: set[str] = set()
        for atom in verb_atoms:
            for alias in ZIL_VERBS.get(atom.upper(), [atom.lower()]):
                if alias not in seen:
                    aliases.append(alias)
                    seen.add(alias)
        verbs = " ".join(aliases)
        if self.action_owner:
            atom, is_room = self.action_owner
            # Rooms keep ``--dspec either`` so their ``<VERB?>`` clauses
            # (e.g. Living Room's ``<VERB? READ>`` on gothic lettering)
            # fire when parser.dobj is something other than the room.
            # Per-object owners use ``--dspec this``: the lamp's
            # ``examine`` clause should fire ONLY when parser.dobj IS
            # the lamp — otherwise it shadows the substrate examine and
            # leaks the lamp's status text for unrelated dobjs.
            dspec = "either" if is_room else "this"
            return f"#!moo verb {verbs} {self._on_for_atom(atom)} --dspec {dspec}"
        # Orphan split: register on the substrate so it dispatches off
        # $zork_thing.  Keep ``--dspec either`` here — the parent substrate
        # routine itself uses ``--dspec this``, but its nested per-clause
        # files need to fire for any dobj the parent forwards to them
        # (otherwise the clause's body never runs and the substrate falls
        # through to the residual default refusal).
        return f"#!moo verb {verbs} {self._on_for_substrate('zork_thing')} --dspec either"

    def _shebang(self) -> str:
        """
        Build the ``#!moo verb`` shebang for the residual full-routine emission.

        :returns: A complete shebang line.
        """
        name = self.routine.name.lower().replace("_", "-")
        if self.action_owner and self._verbs_handled:
            atom, is_room = self.action_owner
            # Subtract per-clause-split verbs so the residual doesn't compete in dispatch.
            residual_verbs = self._verbs_handled - self._clause_split_verbs
            verbs = " ".join(sorted(residual_verbs))
            # Same per-object / per-room split as ``_shebang_verb``:
            # rooms keep ``either`` for the residual's ``<VERB?>`` reach,
            # objects use ``this`` so the residual fires only when
            # parser.dobj IS the action owner.
            dspec = "either" if is_room else "this"
            return f"#!moo verb {verbs} {self._on_for_atom(atom)} --dspec {dspec}"
        name = self._SHEBANG_NAME_OVERRIDE.get(name, name)
        # Drop v- on substrate V-routines so dobj dispatch finds them by the natural name.
        if name.startswith("v-"):
            name = name[2:]
        # Snake-case predicates / hyphenated helpers for dot-syntax dispatch.
        dot_name = routine_dot_name(self.routine.name)
        if dot_name is not None:
            name = dot_name
        # Owner overrides: 0-OBJECT-only / mixed-arity substrate verbs relocate to actor class.
        owner = self.owner_overrides.get(self.routine.name.upper(), "zork_thing")
        # zork_thing substrate verbs need --dspec this; relocated routines need either.
        dspec = "this" if owner == "zork_thing" else "either"
        # Strictly-0-OBJECT verbs (V-YELL, V-INVENTORY, V-VERSION) — emit --dspec none.
        routine_upper = self.routine.name.upper()
        if routine_upper in self.strictly_zero_object:
            dspec = "none"
        # Thread player-verb synonyms in via routine_to_verbs (V-EXAMINE → examine x describe …).
        verbs = name
        aliases = self.routine_to_verbs.get(routine_upper, [])
        if aliases:
            ordered: list[str] = [name]
            for alias in aliases:
                if alias and alias not in ordered:
                    ordered.append(alias)
            verbs = " ".join(ordered)
        return f"#!moo verb {verbs} {self._on_for_substrate(owner)} --dspec {dspec}"

    def _shebang_m(self, m_constant: str) -> str:
        """
        Shebang for an M-/F-clause split file.

        Attaches to the routine's ``action_owner``; orphan routines
        fall back to the ``$zork_thing`` substrate.

        :param m_constant: The M-* / F-* constant the clause handles.
        :returns: A complete shebang line.
        """
        verb = M_TO_VERB.get(m_constant, m_constant.lower().replace("m-", ""))
        # M-BEG/M-LOOK can fire without a parsed dobj — --dspec either lets them.
        if self.action_owner:
            atom, _is_room = self.action_owner
            return f"#!moo verb {verb} {self._on_for_atom(atom)} --dspec either"
        return f"#!moo verb {verb} {self._on_for_substrate('zork_thing')} --dspec either"

    def _need_import(self, name: str) -> None:
        """
        Record ``name`` as an import the emitted body needs.

        :param name: Module/symbol name to import.
        """
        self._imports.add(name)

    # Token patterns scanned post-body to derive imports without per-emission bookkeeping.
    _AUTO_IMPORT_PATTERNS = (
        ("lookup", re.compile(r"\blookup\(")),
        ("context", re.compile(r"\bcontext\.")),
        ("invoked_verb_name", re.compile(r"\binvoked_verb_name\(")),
        ("random", re.compile(r"\brandom\.")),
        ("re", re.compile(r"\bre\.")),
        ("task_time_low", re.compile(r"\btask_time_low\(")),
        ("NoSuchObjectError", re.compile(r"\bNoSuchObjectError\b")),
    )

    def _auto_import(self, lines: list[str]) -> None:
        """
        Re-derive the import set from scratch by scanning ``lines``.

        Resetting (rather than only adding) prunes imports whose
        justifying line was rewritten away during polish.

        :param lines: Generated body / unpack lines to scan.
        """
        # Strip line comments — a primitive in a doc comment shouldn't keep an import alive.
        body = re.sub(r"#.*", "", "\n".join(lines))
        self._imports = set()
        for name, pattern in self._AUTO_IMPORT_PATTERNS:
            if pattern.search(body):
                self._need_import(name)

    # `random` etc. are stdlib — emitted as plain `import X`, not from moo.sdk.
    _STDLIB_IMPORTS = frozenset({"random", "re", "hashlib", "datetime", "time"})

    def _build_imports(self) -> str:
        """
        Render the import block at the top of the verb file.

        :returns: Newline-joined import statements, or ``""`` when no imports needed.
        """
        if not self._imports:
            return ""
        stdlib = sorted(n for n in self._imports if n in self._STDLIB_IMPORTS)
        sdk = sorted(n for n in self._imports if n not in self._STDLIB_IMPORTS)
        lines = [f"import {n}" for n in stdlib]
        if sdk:
            lines.append(f"from moo.sdk import {', '.join(sdk)}")
        return "\n".join(lines)

    def _translate_body(self, forms: list, indent: int = 0) -> list[str]:
        """
        Translate a sequence of forms as statement lines.

        :param forms: ZIL body forms.
        :param indent: Starting indent level (in 4-space units).
        :returns: Generated Python lines.
        """
        # Drop pointless-constant bare atoms at non-tail position (residue of %<COND> macros).
        if forms:
            last_idx = len(forms) - 1
            forms = [f for i, f in enumerate(forms) if i == last_idx or not self._is_pointless_constant(f)]
        lines = []
        for form in forms:
            result = self._translate_stmt(form, indent)
            lines.extend(result)
        if not lines:
            lines.append(self._indent_str(indent) + "pass")
            return lines
        # Python requires a real statement in every block. If every line is
        # a comment, append a ``pass`` so the block parses.
        if all(not line.strip() or line.lstrip().startswith("#") for line in lines):
            lines.append(self._indent_str(indent) + "pass")
        return lines

    @staticmethod
    def _is_pointless_constant(form) -> bool:
        """
        True for bare atoms that translate to a no-op constant expression.

        :param form: AST node to test.
        :returns: ``True`` for bare ``T`` / ``<>`` / ``FALSE`` / ``TRUE`` / int.
        """
        if isinstance(form, int):
            return True
        if isinstance(form, str):
            return form.upper() in ("T", "<>", "FALSE", "TRUE")
        return False

    def _indent_str(self, indent: int) -> str:
        """
        Return the leading whitespace for the given indent level.

        :param indent: Indent level (in 4-space units).
        :returns: A string of ``indent * 4`` spaces.
        """
        return "    " * indent

    def _translate_stmt(self, form: Any, indent: int = 0) -> list[str]:
        """
        Translate one form as a statement, returning lines.

        :param form: ZIL form to translate.
        :param indent: Indent level for the emitted lines.
        :returns: Generated Python lines.
        """
        from . import stmt_handlers

        ind = self._indent_str(indent)

        if form is None or (isinstance(form, list) and not form):
            return []

        # ZIL <#DECL> forms — compiler type hints, no runtime behaviour.
        if isinstance(form, list) and form and isinstance(form[0], str) and form[0].upper() in ("#DECL", "DECL"):
            return []

        if isinstance(form, (int, str)) and not isinstance(form, list):
            # Bare atom/number — ZIL's implicit-return-of-last-expression idiom.
            expr = self._translate_expr(form)
            return [f"{ind}{expr}"]

        # Parenthesised groups are ZIL declaration syntax — no runtime behaviour.
        if isinstance(form, tuple):
            return []

        if not isinstance(form, list):
            return [f"{ind}# ZIL: {form!r}", f"{ind}pass"]

        head = form[0] if form else None
        if not isinstance(head, str):
            expr = self._translate_expr(form)
            return [f"{ind}{expr}"]

        head_upper = head.upper()
        handler = stmt_handlers.HANDLERS.get(head_upper)
        if handler is not None:
            return handler(self, form, ind, indent)
        return stmt_handlers._h_default(self, form, ind, indent)  # pylint: disable=protected-access

    def _translate_expr(self, node: Any) -> str:
        """
        Translate a ZIL node as a Python expression.

        :param node: ZIL AST node (str, int, bool, list, tuple, or None).
        :returns: A Python expression string.
        """
        from . import expr_handlers

        if node is None:
            return "False"
        if isinstance(node, bool):
            return str(node)
        if isinstance(node, int):
            return str(node)
        # Str is a subclass of str — check before the plain `isinstance(str)` branch.
        if isinstance(node, Str):
            return repr(str(node))

        if isinstance(node, str):
            return self._translate_atom(node)

        if isinstance(node, tuple):
            return repr(list(node))
        if not isinstance(node, list):
            return repr(node)
        if not node:
            return "False"

        head = node[0]
        if not isinstance(head, str):
            return repr(node)
        head_upper = head.upper()

        handler = expr_handlers.HANDLERS.get(head_upper)
        if handler is not None:
            return handler(self, node)
        return expr_handlers._h_default(self, node)  # pylint: disable=protected-access

    def _translate_atom(self, node: str) -> str:
        """
        Translate a bare-atom string node to a Python expression.

        Strips ZIL ``,X`` / ``.X`` deref prefix, then classifies in
        order: Boolean, routine-local var, ``,PRSA`` in M-clause, ``V?``
        verb-token index, configured global, M-* event constant,
        room/object atom, named routine, fallback ``zstate_get`` slot.

        :param node: The raw atom string from the AST.
        :returns: A Python expression string.
        """
        atom = node.lstrip(",.")
        upper = atom.upper()
        if upper == "T":
            return "True"
        if upper == "FALSE" or upper == "<>":
            return "False"
        if upper in (p.upper() for p in self.routine.params + self.routine.aux_vars):
            return sanitize_ident(upper)
        if upper == "PRSA" and self._in_m_clause:
            # See explanation/zil-importer (M-clause player-verb binding).
            return "the_player_verb"
        if upper.startswith("V?"):
            # V?<verb> — verb-token index; emit snake-case literal for perform().
            return repr(upper[2:].lower().replace("-", "_"))
        if upper in self._global_map:
            return self._global_map[upper]
        if upper in M_CLAUSES:
            return repr(upper)
        if upper in self.object_atoms:
            # Bootstrap aliases atom-form on every room/object so SOUTH-TEMPLE → "Altar" resolves.
            alias = atom.lower().replace("-", "_")
            return f"lookup({alias!r})"
        if upper in self.routine_atoms:
            # Dot-syntax via routine_dot_name; bare invoke_verb as fallback.
            # When the routine has a substrate verb on a class other than
            # Zork Thing (e.g. echo on Zork Actor), route through that owner
            # — a bare _.zork_thing.X() would AttributeError on dispatch.
            dot = routine_dot_name(upper)
            if dot is not None:
                return f"{substrate_receiver(dot)}.{dot}()"
            return f"{substrate_receiver(atom.lower())}.invoke_verb({atom.lower()!r})"
        return f"context.player.zstate_get({repr(upper)})"

    def _translate_tell(self, form: list) -> str:
        """
        Translate a ``<TELL ...>`` form into a ``print()`` call.

        :param form: The TELL form (head + args).
        :returns: A Python ``print(...)`` expression string.
        """
        parts = form[1:]
        segments: list[str] = []
        has_cr = False

        i = 0
        while i < len(parts):
            item = parts[i]
            if isinstance(item, str) and item.upper() == "CR":
                has_cr = True
                i += 1
                continue
            if isinstance(item, str) and item.upper() == "D":
                # D ,OBJ — description of next argument
                i += 1
                if i < len(parts):
                    obj = self._translate_expr(parts[i])
                    segments.append(f"{obj}.desc()")
                i += 1
                continue
            if isinstance(item, str) and item.upper() == "N":
                # N ,EXPR — numeric value of next argument
                i += 1
                if i < len(parts):
                    val = self._translate_expr(parts[i])
                    segments.append(f"str({val})")
                i += 1
                continue
            if isinstance(item, str) and item.upper() == "C":
                # C ,CHAR — character value
                i += 1
                if i < len(parts):
                    val = self._translate_expr(parts[i])
                    segments.append(f"chr({val})")
                i += 1
                continue
            if isinstance(item, str) and item.upper() == "B":
                # B ,val — byte/number
                i += 1
                if i < len(parts):
                    val = self._translate_expr(parts[i])
                    segments.append(f"str({val})")
                i += 1
                continue
            # Plain string or expression
            expr = self._translate_expr(item)
            segments.append(expr)
            i += 1

        if not segments:
            if has_cr:
                return "print()"
            return "print('', end='')"

        joined = " + ".join(segments)
        if has_cr:
            return f"print({joined})"
        return f"print({joined}, end='')"

    def _translate_short_circuit(self, operands: list, indent: int, negate: bool) -> list[str]:
        """
        Translate ``<AND>`` / ``<OR>`` as a statement chain.

        AND emits a nested ``if`` chain so the trailing operand runs as a
        real statement.  OR emits ``if a: return True`` for each non-last
        operand, then the last operand as a statement — preserving
        first-truthy-wins (``<AND not_invis <OR trans open>>``).

        :param operands: The operands of the AND/OR form (after the head).
        :param indent: Indent level for the emitted lines.
        :param negate: ``True`` for OR (early-return), ``False`` for AND.
        :returns: Generated Python lines.
        """
        if not operands:
            return []
        if len(operands) == 1:
            return self._translate_stmt(operands[0], indent)
        head_expr = self._translate_expr(operands[0])
        ind = self._indent_str(indent)
        inner_ind = self._indent_str(indent + 1)
        if negate:
            # OR: short-circuit on truthy, return early.
            inner = self._translate_short_circuit(operands[1:], indent, negate)
            return [
                f"{ind}if {head_expr}:",
                f"{inner_ind}return True",
            ] + inner
        # AND: short-circuit on falsy; trailing operand runs as a stmt inside the nested if.
        inner = self._translate_short_circuit(operands[1:], indent + 1, negate)
        # Python needs a real statement in the inner block; pad comments-only with `pass`.
        if inner and all(not l.strip() or l.lstrip().startswith("#") for l in inner):
            inner.append(self._indent_str(indent + 1) + "pass")
        elif not inner:
            inner = [self._indent_str(indent + 1) + "pass"]
        return [f"{ind}if {head_expr}:"] + inner

    def _translate_cond(self, form: list, indent: int) -> list[str]:
        """
        Translate ``<COND (cond body...) ... (T body...)>``.

        :param form: The COND form (head + clauses).
        :param indent: Indent level for the emitted lines.
        :returns: Generated Python lines (an ``if/elif/else`` chain).
        """
        ind = self._indent_str(indent)
        lines = []
        clauses = self._splice_zorknumber_macros(form[1:])

        # ZORK-NUMBER is a compile-time constant; pick the matching clause statically.
        zn_clauses = self._zorknumber_select_clauses(clauses)
        if zn_clauses is not None:
            # Bare-constant body in statement context — emit nothing (avoids pointless-stmt).
            if all(self._is_pointless_constant(f) for f in zn_clauses):
                return []
            return self._translate_body(zn_clauses, indent)

        # Sole T/ELSE clause → inline as bare body (drops the `if True:` wrapper).
        meaningful = [c for c in clauses if isinstance(c, (list, tuple)) and c]
        if len(meaningful) == 1 and isinstance(meaningful[0][0], str) and meaningful[0][0].upper() in ("T", "ELSE"):
            body = list(meaningful[0][1:])
            return self._translate_body(body, indent) if body else []

        first_emitted = True
        for clause in clauses:
            if not isinstance(clause, (list, tuple)) or not clause:
                continue
            cond = clause[0]
            body = list(clause[1:])

            # T / ELSE clause
            is_else = isinstance(cond, str) and cond.upper() in ("T", "ELSE")

            if is_else:
                # `else` needs a prior if/elif; fall back to `if True` if the chain didn't start.
                lines.append(f"{ind}else:" if not first_emitted else f"{ind}if True:")
                first_emitted = False
            else:
                cond_expr = self._translate_expr(cond)
                if cond_expr == "None":
                    # Unrecognised condition — emit `if False` placeholder so elif/else still attach.
                    keyword = "if" if first_emitted else "elif"
                    lines.append(f"{ind}{keyword} False:  # pylint: disable=using-constant-test")
                    lines.append(f"{ind}    # ZIL: unrecognised condition {cond!r}")
                    lines.append(f"{ind}    pass")
                    first_emitted = False
                    continue
                keyword = "if" if first_emitted else "elif"
                # Literal-constant tests (e.g. ``<RESTORE>`` always returns
                # False) trip pylint's using-constant-test under --lint.  Add
                # the inline disable since the dead branch is preserved as
                # documentation of what the original ZIL would have done.
                if cond_expr in ("False", "True"):
                    lines.append(f"{ind}{keyword} {cond_expr}:  # pylint: disable=using-constant-test")
                else:
                    lines.append(f"{ind}{keyword} {cond_expr}:")
                first_emitted = False

            if body:
                # Preserve a trailing bare ``T`` / ``<>`` constant.  In ZIL
                # the last expression of a COND clause is the clause's
                # value; when the containing COND is in tail position of a
                # routine, that value is the routine's return.  Action
                # handlers in particular rely on this — ``(T <MOVE ...> ...
                # T)`` in BASKET-F's LOWER branch means "handled, return
                # True (so V-LOWER's hack_hack fallback doesn't fire)".
                # ``_wrap_trailing_return_recursive`` walks the emitted
                # lines and converts the trailing ``True`` / ``False``
                # bare expression into ``return True`` / ``return False``.
                # Bare constants at non-tail positions inside the clause
                # are still dropped (they're noise, like ``<>`` markers in
                # a long action body).
                while len(body) > 1 and self._is_pointless_constant(body[-2]) and self._is_pointless_constant(body[-1]):
                    body = body[:-1]
                if body:
                    body_lines = self._translate_body(body, indent + 1)
                    lines.extend(body_lines)
                else:
                    lines.append(f"{ind}    pass")
            else:
                lines.append(f"{ind}    pass")

        return lines

    def _zorknumber_select_clauses(self, clauses):
        """
        Compile-time selection of a ZORK-NUMBER COND.

        :param clauses: The COND clauses (after the head).
        :returns: The chosen clause's body forms, or ``None`` when the
            COND isn't entirely ZORK-NUMBER + T/ELSE clauses.
        """
        zork_number = self.game_config.zork_number
        meaningful = [c for c in clauses if isinstance(c, (list, tuple)) and c]
        if not meaningful:
            return None
        selected_body = None
        fallback_body = None
        for clause in meaningful:
            test = clause[0]
            body = list(clause[1:])
            is_zn = (
                isinstance(test, list)
                and len(test) >= 3
                and isinstance(test[0], str)
                and test[0].upper() in ("==?", "EQUAL?")
                and isinstance(test[1], str)
                and test[1].upper() == "ZORK-NUMBER"
                and isinstance(test[2], int)
            )
            is_else = isinstance(test, str) and test.upper() in ("T", "ELSE")
            if not is_zn and not is_else:
                return None
            if is_zn and test[2] == zork_number and selected_body is None:
                selected_body = body
            elif is_else and fallback_body is None:
                fallback_body = body
        chosen = selected_body if selected_body is not None else fallback_body
        if chosen is None:
            return []
        # Flatten one tuple level — substrate ``'<...>'`` quoted bodies arrive
        # as a single tuple wrapping the real form list.
        if len(chosen) == 1 and isinstance(chosen[0], tuple):
            return list(chosen[0])
        return chosen

    def _splice_zorknumber_macros(self, clauses):
        """
        Resolve substrate ``%<COND ... ZORK-NUMBER ...>`` macros at translate time.

        The tokenizer drops ``%`` / ``'``, so the inner COND would
        otherwise become the outer COND's first conditional.  For Zork 1
        (current target) ``ZORK-NUMBER`` is ``1``.

        :param clauses: The COND clauses to splice through.
        :returns: The clauses with ZORK-NUMBER macros expanded.
        """
        zork_number = self.game_config.zork_number
        spliced = []
        for clause in clauses:
            if (
                isinstance(clause, list)
                and len(clause) >= 2
                and isinstance(clause[0], str)
                and clause[0].upper() == "COND"
            ):
                # ``[COND, (test, body), (T, body), ...]`` — pick matching body.
                replacement = None
                for sub in clause[1:]:
                    if not isinstance(sub, (list, tuple)) or len(sub) < 2:
                        continue
                    test = sub[0]
                    body = sub[1]
                    is_match = False
                    if isinstance(test, str) and test.upper() in ("T", "ELSE"):
                        is_match = True
                    elif (
                        isinstance(test, list)
                        and len(test) >= 3
                        and isinstance(test[0], str)
                        and test[0].upper() in ("==?", "EQUAL?")
                        and isinstance(test[1], str)
                        and test[1].upper() == "ZORK-NUMBER"
                        and test[2] == zork_number
                    ):
                        is_match = True
                    if is_match:
                        replacement = body
                        break
                if replacement is not None:
                    # Replacement may be tuple (`(...)` group) or list — both splice as one clause.
                    spliced.append(replacement)
                    continue
            spliced.append(clause)
        return spliced

    _CONTROL_PREFIXES = ("if ", "elif ", "else", "while ", "for ", "return", "raise", "pass", "break", "continue", "#")
    # `var = expr` only — negative lookbehind rules out ==, !=, <=, >=, walrus.
    _ASSIGN_RE = re.compile(r"^[A-Za-z_][\w.\[\]]*\s*(?<![=!<>])=(?!=)")

    def _line_indent(self, line: str) -> int:
        """
        Return the leading-space indent of ``line`` rounded down to 4.

        :param line: A generated Python line.
        :returns: Indent level (in 4-space units).
        """
        n = len(line) - len(line.lstrip(" "))
        return n // 4

    # Captures `lookup("name")` or `lookup('name')` calls; group(2) is the atom.
    _LOOKUP_RE = re.compile(r"\blookup\((['\"])([^'\"]+)\1\)")

    def _fix_return_print(self, lines: list[str]) -> list[str]:
        """
        Split ``return print(...)`` into ``print(...)`` then ``return``.

        ``print()`` returns ``None``; the wrap only carried exit
        semantics, not a value.

        :param lines: Generated body lines.
        :returns: The body with the rewrite applied.
        """
        out = []
        for line in lines:
            stripped = line.lstrip(" ")
            indent_chars = line[: len(line) - len(stripped)]
            if stripped.startswith("return print("):
                out.append(indent_chars + stripped[len("return ") :])
                out.append(indent_chars + "return")
            else:
                out.append(line)
        return out

    # `    print(<EXPR>, end='')` — group(1) indent, group(2) EXPR.
    _PRINT_END_RE = re.compile(r"^(\s*)print\((.+), end=(?:''|\"\")\)$")

    def _merge_adjacent_prints(self, lines: list[str]) -> list[str]:
        """
        Merge runs of ``print(EXPR, end='')`` lines at the same indent.

        ZIL's ``<TELL "X" ,SCORE " Y" ,MOVES>`` emits a per-segment
        print, but each becomes a separate writer() call — and the
        shell renders each on its own line.  Folding into one print
        matches ZIL's TELL semantics.  Numeric exprs are already
        ``str()``-wrapped, so ``+`` concatenation is well-typed.

        :param lines: Generated body lines.
        :returns: The body with adjacent print runs merged.
        """
        out: list[str] = []
        i = 0
        while i < len(lines):
            m = self._PRINT_END_RE.match(lines[i])
            if not m:
                out.append(lines[i])
                i += 1
                continue
            indent_str = m.group(1)
            exprs = [m.group(2)]
            j = i + 1
            while j < len(lines):
                m2 = self._PRINT_END_RE.match(lines[j])
                if not m2 or m2.group(1) != indent_str:
                    break
                exprs.append(m2.group(2))
                j += 1
            if len(exprs) > 1:
                joined = " + ".join(exprs)
                out.append(f"{indent_str}print({joined}, end='')")
            else:
                out.append(lines[i])
            i = j
        return out

    # `prso.METHOD(args)` / `prsi.METHOD(args)` → wrap to short-circuit when
    # the dobj/iobj is missing.  Negative lookbehind keeps the match from
    # tripping on already-wrapped forms or compound identifier suffixes.
    _PRSO_PRSI_METHOD_RE = re.compile(r"(?<![\w.])(prso|prsi)\.(\w+)\(([^()]*)\)")

    # Methods whose result is concatenated into TELL output, so the missing-
    # PRSO/PRSI fallback must be ``""`` rather than ``None`` to keep string
    # ``+`` from raising ``TypeError: can only concatenate str (not "NoneType")``.
    _STRING_RETURNING_METHODS = frozenset({"desc", "title"})

    def _null_safe_iobj_methods(self, lines: list[str]) -> list[str]:
        """
        Wrap ``prso.METHOD(...)`` / ``prsi.METHOD(...)`` so a missing
        dobj/iobj doesn't crash ZIL ``<FSET? ,PRSI ,OPENBIT>``-style
        flag tests.  ``prsi.flag("open")`` → ``(prsi.flag("open") if prsi else None)``.

        For methods that return strings (``.desc()`` / ``.title()``) the
        fallback is ``""`` instead of ``None`` so the result composes
        safely with ``+`` inside translated TELL output.

        :param lines: Generated body lines.
        :returns: The body with the rewrite applied.
        """

        def repl(m: re.Match) -> str:
            var = m.group(1)
            method = m.group(2)
            args = m.group(3)
            fallback = '""' if method in self._STRING_RETURNING_METHODS else "None"
            return f"({var}.{method}({args}) if {var} else {fallback})"

        out: list[str] = []
        for line in lines:
            stripped = line.lstrip()
            # Don't wrap the hoist binding itself or our own None-guard.
            if stripped.startswith(("prso = ", "prsi = ", "if prso is None", "if prsi is None")):
                out.append(line)
                continue
            out.append(self._PRSO_PRSI_METHOD_RE.sub(repl, line))
        return out

    def _replace_self_lookup_with_this(self, lines: list[str]) -> list[str]:
        """
        Rewrite self-referential ``lookup("atom")`` to ``this`` for owned verbs.

        :param lines: Generated body lines.
        :returns: The body with self-references rewritten to ``this``.
        """
        if not self.action_owner:
            return lines
        owner_atom, _is_room = self.action_owner
        target = owner_atom.lower().replace("-", "_")
        # Match the atom either as-is or with hyphens-to-underscores.
        targets = {owner_atom.lower(), target}

        def repl(m: re.Match) -> str:
            return "this" if m.group(2).lower() in targets else m.group(0)

        return [self._LOOKUP_RE.sub(repl, line) for line in lines]

    def _cache_repeated_lookups(self, lines: list[str]) -> tuple[list[str], list[str]]:
        """
        Hoist ``lookup("X")`` calls used 2+ times into a local variable.

        Hoist lines go at the top so the variable is in scope for every
        reference.

        :param lines: Generated body lines.
        :returns: ``(hoist_lines, rewritten_lines)``.
        """
        counts: dict[str, int] = {}
        for line in lines:
            for m in self._LOOKUP_RE.finditer(line):
                counts[m.group(2)] = counts.get(m.group(2), 0) + 1

        hoisted: dict[str, str] = {}
        for atom, count in sorted(counts.items()):
            if count < 2:
                continue
            ident = re.sub(r"[^a-z0-9_]", "_", atom.lower())
            if not ident or ident[0].isdigit():
                continue
            # Avoid colliding with python keywords or builtins.
            if ident in PY_KEYWORDS or ident in PY_BUILTIN_SHADOWS:
                ident = ident + "_o"
            hoisted[atom] = ident

        if not hoisted:
            return [], lines

        def repl(m: re.Match) -> str:
            atom = m.group(2)
            return hoisted.get(atom, m.group(0))

        rewritten = [self._LOOKUP_RE.sub(repl, line) for line in lines]
        hoist_lines = [f'{var} = lookup("{atom}")' for atom, var in hoisted.items()]
        return hoist_lines, rewritten

    def _maybe_hoist_parser(self, lines: list[str]) -> tuple[list[str], list[str]]:
        """
        Hoist ``parser = context.parser`` and rewrite refs.

        :param lines: Generated body lines.
        :returns: ``(hoist_lines, rewritten_lines)``; ``hoist_lines`` is
            empty when no rewrite is needed.
        """
        if not any("context.parser." in line for line in lines):
            return [], lines
        rewritten = [line.replace("context.parser.", "parser.") for line in lines]
        return ["parser = context.parser"], rewritten

    def _maybe_hoist_player(self, lines: list[str]) -> tuple[list[str], list[str]]:
        """
        Hoist ``player = context.player`` and rewrite refs.

        :param lines: Generated body lines.
        :returns: ``(hoist_lines, rewritten_lines)``; ``hoist_lines`` is
            empty when no rewrite is needed.
        """
        if not any("context.player" in line for line in lines):
            return [], lines
        rewritten = [line.replace("context.player", "player") for line in lines]
        return ["player = context.player"], rewritten

    _PRSO_RE = re.compile(r"(?<!\w)prso(?!\w)")
    _PRSI_RE = re.compile(r"(?<!\w)prsi(?!\w)")

    def _maybe_hoist_prso(self, lines: list[str]) -> list[str]:
        """
        Emit a ``prso = …`` binding when any line references the local name
        ``prso``.  Wraps ``get_dobj()`` in a try/except so a direction word
        (``up`` / ``north``) that doesn't resolve to a real object yields
        ``prso = None`` instead of raising ``NoSuchObjectError`` before the
        verb body runs.

        :param lines: Generated body lines.
        :returns: Hoist lines (possibly empty).
        """
        if not any(self._PRSO_RE.search(line) for line in lines):
            return []
        return [
            "try:",
            "    prso = context.parser.get_dobj() if context.parser.has_dobj_str() else None",
            "except NoSuchObjectError:",
            "    prso = None",
        ]

    def _maybe_hoist_prsi(self, lines: list[str]) -> list[str]:
        """
        Emit a ``prsi = …`` binding when any line references the local name
        ``prsi``.  Wraps ``get_iobj()`` in a try/except for the same reason
        as :py:meth:`_maybe_hoist_prso`.

        :param lines: Generated body lines.
        :returns: Hoist lines (possibly empty).
        """
        if not any(self._PRSI_RE.search(line) for line in lines):
            return []
        return [
            "try:",
            "    prsi = context.parser.get_iobj() if context.parser.has_iobj() else None",
            "except NoSuchObjectError:",
            "    prsi = None",
        ]

    def _maybe_inject_prso_guard(self, body_lines: list[str], unpack_lines: list[str]) -> list[str]:
        """
        Prepend a missing-dobj early-return when the residual is a
        ``--dspec this`` substrate verb that references ``prso``.

        Without this, attribute access on ``prso`` (e.g. ``prso.location``)
        AttributeErrors when the user types the verb with no object.

        :param body_lines: Generated body lines after polish.
        :param unpack_lines: Prelude unpack lines (checked for the
            ``prso`` hoist binding).
        :returns: ``body_lines`` with the guard prepended when applicable.
        """
        if self.action_owner:
            return body_lines
        routine_upper = self.routine.name.upper()
        if routine_upper in self.strictly_zero_object:
            return body_lines
        owner = self.owner_overrides.get(routine_upper, "zork_thing")
        if owner != "zork_thing":
            return body_lines
        if not any(self._PRSO_RE.search(line) for line in unpack_lines + body_lines):
            return body_lines
        # Human-readable verb name for the message — drop V- prefix and
        # snake-ify.  Helpers without V- prefix (idrop, itake) fall
        # through to a generic refusal so a stray helper-name doesn't
        # leak through.
        if routine_upper.startswith("V-"):
            verb_human = routine_upper.removeprefix("V-").lower().replace("-", " ")
            bare_message = f'"What do you want to {verb_human}?"'
        else:
            bare_message = '"I don\'t know how to do that."'
        # Two paths to prso==None: bare verb (no dobj_str) → ask; dobj_str
        # given but unresolved (caught by the hoist's try/except) → echo
        # the canonical parser-error message.
        #
        # PRE-X routines are invoked by their V-X parent as
        # ``if _.zork_thing.invoke_verb("pre_x"): return``; the parent
        # treats a truthy return as "PRE-X handled the command, do not
        # continue".  Emit ``return True`` for PRE-X so the parent does
        # not fall through to its default refusal (e.g. V-TURN's
        # "This has no effect." after PRE-TURN already printed the
        # missing-dobj message).  V-X routines themselves are terminal —
        # keep their bare ``return``.
        guard_return = "    return True" if routine_upper.startswith("PRE-") else "    return"
        guard = [
            "if prso is None:",
            "    if context.parser is not None and context.parser.has_dobj_str():",
            '        print("There is no \'" + context.parser.dobj_str + "\' here.")',
            "    else:",
            f"        print({bare_message})",
            guard_return,
            "",
        ]
        return guard + body_lines

    def _polish(self, body_lines: list[str], unpack_lines: list[str]) -> tuple[list[str], list[str]]:
        """
        Apply readability transforms.

        Order: pure line rewrites first; then lookup caching across
        unpack+body; then parser/player hoists so they see the final body.

        :param body_lines: Generated body lines.
        :param unpack_lines: Param/aux unpack lines emitted at the top.
        :returns: ``(polished_body_lines, polished_unpack_lines)``.
        """
        body_lines = self._fix_return_print(body_lines)
        body_lines = self._replace_self_lookup_with_this(body_lines)
        body_lines = self._merge_adjacent_prints(body_lines)
        body_lines = self._null_safe_iobj_methods(body_lines)

        cache_lines, combined = self._cache_repeated_lookups(unpack_lines + body_lines)
        unpack_lines = combined[: len(unpack_lines)]
        body_lines = combined[len(unpack_lines) :]

        # prso/prsi hoists first — they emit `context.parser.` so the
        # parser hoist below sees them and rewrites to `parser.`.
        prso_hoist = self._maybe_hoist_prso(unpack_lines + body_lines)
        prsi_hoist = self._maybe_hoist_prsi(unpack_lines + body_lines)
        prso_len = len(prso_hoist)
        prsi_len = len(prsi_hoist)
        unpack_total = len(unpack_lines)
        body_total = len(body_lines)

        parser_hoist, combined = self._maybe_hoist_parser(unpack_lines + body_lines + prso_hoist + prsi_hoist)
        unpack_lines = combined[:unpack_total]
        body_lines = combined[unpack_total : unpack_total + body_total]
        prso_hoist = combined[unpack_total + body_total : unpack_total + body_total + prso_len]
        prsi_hoist = combined[unpack_total + body_total + prso_len : unpack_total + body_total + prso_len + prsi_len]

        player_hoist, combined = self._maybe_hoist_player(unpack_lines + body_lines + prso_hoist + prsi_hoist)
        unpack_lines = combined[:unpack_total]
        body_lines = combined[unpack_total : unpack_total + body_total]
        prso_hoist = combined[unpack_total + body_total : unpack_total + body_total + prso_len]
        prsi_hoist = combined[unpack_total + body_total + prso_len : unpack_total + body_total + prso_len + prsi_len]

        # Prelude (hoists + cache) goes above unpack so vars are in scope for defaults.
        prelude = player_hoist + parser_hoist + prso_hoist + prsi_hoist + cache_lines
        if prelude:
            unpack_lines = prelude + unpack_lines
        return body_lines, unpack_lines

    def _wrap_trailing_return_recursive(self, lines: list[str], indent: int) -> list[str]:
        """
        Wrap each branch's trailing expression in ``return``.

        Implements ZIL's implicit-return-of-last-expression.  See
        :doc:`/explanation/zil-importer`.

        :param lines: Generated body lines (mutated in place).
        :param indent: Current scope's indent level.
        :returns: ``lines`` with trailing expressions wrapped.
        """
        if not lines:
            return lines
        # Last non-blank/non-comment line at this indent = the routine's tail at this scope.
        tail_idx: int | None = None
        for idx in range(len(lines) - 1, -1, -1):
            line = lines[idx]
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            if self._line_indent(line) == indent:
                tail_idx = idx
                break
        if tail_idx is None:
            return lines
        tail_line = lines[tail_idx]
        stripped = tail_line.strip()
        if stripped.startswith(self._CONTROL_PREFIXES) and not stripped.startswith(
            ("if ", "elif ", "else", "while ", "for ")
        ):
            return lines
        if stripped.startswith(("if ", "elif ", "else", "while ", "for ")):
            # Recurse only into the tail's own construct; earlier independent if-blocks
            # at this indent must not be wrapped.
            if stripped.startswith(("while ", "for ")):
                chain_openers = [tail_idx]
            else:
                # if/elif/else chain: walk back from tail collecting else/elif until the if.
                chain_openers = []
                walk = tail_idx
                while walk >= 0:
                    line = lines[walk]
                    if not line.strip() or line.lstrip().startswith("#"):
                        walk -= 1
                        continue
                    line_indent = self._line_indent(line)
                    if line_indent > indent:
                        walk -= 1
                        continue
                    if line_indent < indent:
                        break
                    stripped_l = line.lstrip()
                    if stripped_l.startswith("if "):
                        chain_openers.append(walk)
                        break
                    if stripped_l.startswith(("elif ", "else")):
                        chain_openers.append(walk)
                        walk -= 1
                        continue
                    break
                chain_openers.reverse()
            for opener_idx in chain_openers:
                block_end = opener_idx + 1
                while block_end < len(lines):
                    bl = lines[block_end]
                    if bl.strip() and self._line_indent(bl) <= indent:
                        break
                    block_end += 1
                nested = self._wrap_trailing_return_recursive(lines[opener_idx + 1 : block_end], indent + 1)
                lines[opener_idx + 1 : block_end] = nested
            return lines
        # Bare trailing expression — wrap in `return`; skip plain `x = y` assignments.
        if self._ASSIGN_RE.match(stripped):
            return lines
        prefix = " " * (indent * 4)
        lines[tail_idx] = f"{prefix}return {stripped}"
        return lines

    def _find_dispatch(self, forms: list, allowed: set[str]) -> list | None:
        """
        Find a top-level COND with at least one clause testing ``allowed``.

        :param forms: Body forms to walk.
        :param allowed: Constant set the dispatch must test against.
        :returns: The matching COND form, or ``None``.
        """
        for form in forms:
            if not isinstance(form, list) or not form:
                continue
            head = str(form[0]).upper()
            if head == "COND":
                for clause in form[1:]:
                    if not isinstance(clause, (list, tuple)) or not clause:
                        continue
                    cond = clause[0]
                    if isinstance(cond, (list, tuple)):
                        for item in cond:
                            if isinstance(item, str) and item in allowed:
                                return form
                    elif isinstance(cond, str) and cond in allowed:
                        return form
        return None

    def _find_m_dispatch(self, forms: list) -> list | None:
        """
        Find a top-level COND that dispatches on RARG/M-* constants.

        :param forms: Body forms to walk.
        :returns: The matching COND form, or ``None``.
        """
        return self._find_dispatch(forms, M_CLAUSES)

    def _find_f_dispatch(self, forms: list) -> list | None:
        """
        Find a top-level COND that dispatches on MODE/F-* constants.

        :param forms: Body forms to walk.
        :returns: The matching COND form, or ``None``.
        """
        return self._find_dispatch(forms, F_CLAUSES)

    def _extract_clause(self, forms: list, constant: str, allowed: set[str]) -> list | None:
        """
        Return body forms for the given M-* or F-* clause, or ``None``.

        :param forms: Body forms to walk.
        :param constant: The M-* / F-* constant to extract.
        :param allowed: The full constant set the dispatch tests against.
        :returns: Clause body forms, or ``None`` when the clause is absent.
        """
        dispatch = self._find_dispatch(forms, allowed)
        if dispatch is None:
            return None
        for clause in dispatch[1:]:
            if not isinstance(clause, (list, tuple)) or not clause:
                continue
            cond = clause[0]
            body = list(clause[1:])
            if isinstance(cond, str) and cond.upper() == constant:
                return body
            if isinstance(cond, (list, tuple)):
                for item in cond:
                    if isinstance(item, str) and item.upper() == constant:
                        return body
        return None

    def _extract_m_clause(self, forms: list, m_constant: str) -> list | None:
        """
        Return body forms for the given M-* clause, or ``None``.

        :param forms: Body forms to walk.
        :param m_constant: The M-* constant whose clause to extract.
        :returns: Clause body forms, or ``None``.
        """
        return self._extract_clause(forms, m_constant, M_CLAUSES)

    def _extract_f_clause(self, forms: list, f_constant: str) -> list | None:
        """
        Return body forms for the given F-* clause, or ``None``.

        :param forms: Body forms to walk.
        :param f_constant: The F-* constant whose clause to extract.
        :returns: Clause body forms, or ``None``.
        """
        return self._extract_clause(forms, f_constant, F_CLAUSES)

    def _translate_flag_name(self, node: Any) -> str:
        """
        Translate a ZIL flag atom to a DjangoMOO property name string.

        For ``.<var>`` derefs of routine params/aux vars, emits the bare
        variable so ``<FSET? .RM .AV>`` becomes ``flag(rm, av)``.

        :param node: Flag-atom AST node.
        :returns: A Python expression: ``"propname"`` or a bare local-var name.
        """
        if isinstance(node, list) and node:
            # ,FLAGNAME parses as [FLAGNAME] in some contexts — unwrap.
            node = node[0] if len(node) == 1 else node
        if isinstance(node, str):
            # `.X` deref of a routine param/aux var — emit the local name.
            if node.startswith("."):
                bare = node[1:]
                local_atoms = {p.upper() for p in self.routine.params + self.routine.aux_vars}
                if bare.upper() in local_atoms:
                    return sanitize_ident(bare.upper())
            upper = node.lstrip(",.").upper()
            if upper in FLAG_PROPERTIES:
                prop, _val = FLAG_PROPERTIES[upper]
                return repr(prop)
            if upper.startswith("P?"):
                upper = upper[2:]
            return repr(upper.lower().replace("-", "_"))
        return repr(str(node).lower())

    def _translate_prop_name(self, node: Any) -> str:
        """
        Translate a ZIL ``P?NAME`` atom to a DjangoMOO property-name string.

        :param node: Property-atom AST node.
        :returns: A Python string-literal expression.
        """
        if isinstance(node, list) and node:
            node = node[0] if len(node) == 1 else node
        if isinstance(node, str):
            upper = node.upper()
            if upper in PROP_MAP:
                return repr(PROP_MAP[upper])
            if upper.startswith("P?"):
                return repr(upper[2:].lower().replace("-", "_"))
            return repr(upper.lower().replace("-", "_"))
        return repr(str(node).lower())


def translate_routine(routine: ZilRoutine, *, game_config: GameConfig | None = None) -> str:
    """
    Translate a ZilRoutine to a complete verb-file string.

    :param routine: The ZIL routine IR to translate.
    :param game_config: Optional per-game configuration; defaults to ``ZORK1_CONFIG``.
    :returns: Complete verb-file source.
    """
    return ZilTranslator(routine, game_config=game_config).translate()


def translate_m_clause(routine: ZilRoutine, m_constant: str, *, game_config: GameConfig | None = None) -> str:
    """
    Translate one M-* clause from an ACTION routine.

    :param routine: The ZIL routine IR to translate.
    :param m_constant: The M-* constant whose clause to extract.
    :param game_config: Optional per-game configuration; defaults to ``ZORK1_CONFIG``.
    :returns: Verb-file source for the clause, or ``""`` for a no-op.
    """
    return ZilTranslator(routine, game_config=game_config).translate_m_clause(m_constant)


def translate_f_clause(routine: ZilRoutine, f_constant: str, *, game_config: GameConfig | None = None) -> str:
    """
    Translate one F-* combat clause from a per-villain ACTION routine.

    :param routine: The ZIL routine IR to translate.
    :param f_constant: The F-* constant whose clause to extract.
    :param game_config: Optional per-game configuration; defaults to ``ZORK1_CONFIG``.
    :returns: Verb-file source for the clause, or ``""`` for a no-op.
    """
    return ZilTranslator(routine, game_config=game_config).translate_f_clause(f_constant)


def has_m_dispatch(routine: ZilRoutine) -> bool:
    """
    Return True if routine dispatches on M-* constants.

    :param routine: The ZIL routine IR.
    :returns: ``True`` when an M-* dispatch COND is present.
    """
    return ZilTranslator(routine).has_m_dispatch()


def has_f_dispatch(routine: ZilRoutine) -> bool:
    """
    Return True if routine dispatches on F-* combat constants.

    :param routine: The ZIL routine IR.
    :returns: ``True`` when an F-* dispatch COND is present.
    """
    return ZilTranslator(routine).has_f_dispatch()


def m_constants_found(routine: ZilRoutine) -> list[str]:
    """
    Return list of M-* constants handled by an ACTION routine.

    :param routine: The ZIL routine IR.
    :returns: M-* constants in clause order, or ``[]``.
    """
    return ZilTranslator(routine).m_constants_found()
