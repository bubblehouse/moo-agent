"""
Statement-level form-head handlers.

``ZilTranslator._translate_stmt`` dispatches through ``HANDLERS`` keyed
on the form's head atom; unknown heads fall through to the
expression-as-statement fallback.  See :doc:`/reference/zil-importer`
(Translator package layout).

Every ``_h_*`` handler in this module follows the ``Handler`` protocol
below.  Per-handler docstrings describe only the form-specific
behaviour; the ``Handler``-protocol parameters and return type are
documented once on the alias and not repeated.
"""
# Handlers were split out of ``ZilTranslator`` but still reach into its
# private ``_translate_expr`` API — they're effectively the same module
# by intent.
# pylint: disable=protected-access

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from . import daemon_modes
from .constants import M_TO_VERB
from .identifiers import sanitize_ident

if TYPE_CHECKING:
    from . import ZilTranslator


Handler = Callable[["ZilTranslator", list, str, int], list[str]]
"""
Statement-handler protocol.

:param translator: The active :class:`ZilTranslator` instance.
:param form: ZIL form to translate; ``form[0]`` is the head atom.
:param ind: Indent string (already expanded) for the emitted lines.
:param indent: Integer indent level — used only by handlers that
    recurse into nested statement bodies.
:returns: Generated Python lines for the form.
"""


def _h_rtrue(_t: "ZilTranslator", _form: list, ind: str, _indent: int) -> list[str]:
    """Translate ``<RTRUE>`` as ``return True``."""
    return [f"{ind}return True"]


def _h_rfalse(t: "ZilTranslator", _form: list, ind: str, _indent: int) -> list[str]:
    """
    Translate ``<RFALSE>``.

    In an ACTION routine this means "fall through to V-<verb>", so the
    handler emits ``return passthrough()`` (substrate dispatch).
    M-clause splits skip the re-dispatch since they don't own the verb.
    """
    if t.action_owner and t._verbs_handled and not t._in_m_clause:
        return [f"{ind}return passthrough()"]
    return [f"{ind}return False"]


def _h_rfatal(_t: "ZilTranslator", _form: list, ind: str, _indent: int) -> list[str]:
    """
    Translate ``<RFATAL>`` as ``return False``.

    Without this stmt handler the expr handler emits the bare integer ``2``
    (ZIL's fatal sentinel) which lands as a no-op statement and lets the
    caller fall through — e.g. ITAKE's "not takeable" branch printed the
    V-CARVE rebuke but still moved the dobj into the player's inventory.
    """
    return [f"{ind}return False"]


def _h_return(t: "ZilTranslator", form: list, ind: str, _indent: int) -> list[str]:
    """Translate ``<RETURN [value]>`` — ``break`` inside REPEAT, ``return`` otherwise."""
    if len(form) <= 1 and t._repeat_depth > 0:
        return [f"{ind}break"]
    val = t._translate_expr(form[1]) if len(form) > 1 else "None"
    return [f"{ind}return {val}"]


def _h_tell(t: "ZilTranslator", form: list, ind: str, _indent: int) -> list[str]:
    """Translate ``<TELL ...>`` as a ``print(...)`` statement."""
    return [f"{ind}{t._translate_tell(form)}"]


def _h_crlf(_t: "ZilTranslator", _form: list, ind: str, _indent: int) -> list[str]:
    """Translate ``<CRLF>`` as a bare ``print()``."""
    return [f"{ind}print()"]


def _h_print(t: "ZilTranslator", form: list, ind: str, _indent: int) -> list[str]:
    """Translate ``<PRINT val>`` as ``print(val, end='')``."""
    val = t._translate_expr(form[1]) if len(form) > 1 else '""'
    return [f"{ind}print({val}, end='')"]


def _h_printi(t: "ZilTranslator", form: list, ind: str, _indent: int) -> list[str]:
    """Translate ``<PRINTI "lit">`` as ``print("lit", end='')``.

    ZIL's PRINTI is "print immediate string literal, no CRLF". The
    `<PRINTI ">"><READ ...>` prompt/wait pattern (V-SCORE, V-QUIT) is
    handled at the source level — wiring it to ``open_input`` is a
    separate concern.
    """
    val = t._translate_expr(form[1]) if len(form) > 1 else '""'
    return [f"{ind}print({val}, end='')"]


def _h_print_cr(t: "ZilTranslator", form: list, ind: str, _indent: int) -> list[str]:
    """Translate ``<PRINTR val>`` / ``<PRINT-CR val>`` as ``print(val)``."""
    val = t._translate_expr(form[1]) if len(form) > 1 else '""'
    return [f"{ind}print({val})"]


def _h_printn(t: "ZilTranslator", form: list, ind: str, _indent: int) -> list[str]:
    """Translate ``<PRINTN val>`` as ``print(str(val), end='')``."""
    val = t._translate_expr(form[1]) if len(form) > 1 else "0"
    return [f"{ind}print(str({val}), end='')"]


def _h_printc(t: "ZilTranslator", form: list, ind: str, _indent: int) -> list[str]:
    """Translate ``<PRINTC val>`` as ``print(chr(val), end='')``."""
    val = t._translate_expr(form[1]) if len(form) > 1 else "0"
    return [f"{ind}print(chr({val}), end='')"]


def _h_printd(t: "ZilTranslator", form: list, ind: str, _indent: int) -> list[str]:
    """Translate ``<PRINTD obj>`` as ``print(obj.desc(), end='')``."""
    obj = t._translate_expr(form[1]) if len(form) > 1 else "None"
    return [f"{ind}print({obj}.desc(), end='')"]


def _h_print_contents(t: "ZilTranslator", form: list, ind: str, _indent: int) -> list[str]:
    """
    Translate ``<PRINT-CONTENTS obj>`` as ``print(_.thing.print_contents(obj), end='')``.

    Wrapping the sub-verb result in the caller's ``print`` keeps the
    listing inside the caller's ``_print_`` collector — otherwise the
    sub-verb's collector flushes first and the listing prints BEFORE
    the surrounding ``Opening the X reveals ...`` sentence.  See the
    hand-written ``print_contents`` verb (returns a string, no side
    effects).
    """
    obj = t._translate_expr(form[1]) if len(form) > 1 else "None"
    return [f"{ind}print(_.thing.print_contents({obj}), end='')"]


def _h_apply(t: "ZilTranslator", form: list, ind: str, indent: int) -> list[str]:
    """
    Translate ``<APPLY <GETP obj ,P?ACTION> ,M-X>`` as a guarded ``invoke_verb``.

    Falls through to ``_h_default`` for unhandled APPLY shapes.
    """
    if len(form) < 3:
        return _h_default(t, form, ind, indent)
    target = form[1]
    arg = form[2]
    verb_name = None
    if isinstance(arg, str):
        verb_name = M_TO_VERB.get(arg.lstrip(",.").upper())
    if verb_name and isinstance(target, list) and len(target) >= 3:
        t_head = target[0]
        if isinstance(t_head, str) and t_head.upper() in ("GETP", "GETPT"):
            obj_expr = t._translate_expr(target[1])
            return [
                f"{ind}# ZIL: <APPLY ...>",
                f"{ind}if {obj_expr} is not None and {obj_expr}.has_verb({verb_name!r}, recurse=False):",
                f"{ind}    {obj_expr}.invoke_verb({verb_name!r})",
            ]
    return _h_default(t, form, ind, indent)


def _h_cond(t: "ZilTranslator", form: list, _ind: str, indent: int) -> list[str]:
    """Translate ``<COND>`` via :meth:`ZilTranslator._translate_cond`."""
    return t._translate_cond(form, indent)


def _h_and(t: "ZilTranslator", form: list, _ind: str, indent: int) -> list[str]:
    """Translate ``<AND>`` as a nested ``if`` chain (statement context)."""
    return t._translate_short_circuit(form[1:], indent, negate=False)


def _h_or(t: "ZilTranslator", form: list, _ind: str, indent: int) -> list[str]:
    """Translate ``<OR>`` as an early-return chain (statement context)."""
    return t._translate_short_circuit(form[1:], indent, negate=True)


def _h_not(t: "ZilTranslator", form: list, ind: str, _indent: int) -> list[str]:
    """Translate ``<NOT val>`` as a bare ``not val`` expression statement."""
    val = t._translate_expr(form[1]) if len(form) > 1 else "True"
    return [f"{ind}not {val}"]


def _h_repeat(t: "ZilTranslator", form: list, ind: str, indent: int) -> list[str]:
    """Translate ``<REPEAT … >`` as ``while True:`` with a sandbox-time guard."""
    body = list(form[2:]) if len(form) > 2 else list(form[1:])
    t._repeat_depth += 1
    try:
        inner = t._translate_body(body, indent + 1)
    finally:
        t._repeat_depth -= 1
    # Sandbox guard: a runaway <REPEAT> would consume the celery worker pool.
    inner_ind = t._indent_str(indent + 1)
    routine_label = t.routine.name if t.routine and t.routine.name else "<unknown>"
    guard = [
        f"{inner_ind}if task_time_low():",
        f'{inner_ind}    print("[zil] long-running loop in {routine_label}; aborting (bug — please report).")',
        f"{inner_ind}    return False",
    ]
    return [f"{ind}while True:"] + guard + inner


def _h_prog(t: "ZilTranslator", form: list, _ind: str, indent: int) -> list[str]:
    """Translate ``<PROG>`` (block scope with optional locals) as inline body lines."""
    body = list(form[2:]) if len(form) > 2 and isinstance(form[1], (list, tuple)) else list(form[1:])
    return t._translate_body(body, indent)


def _h_map_contents(t: "ZilTranslator", form: list, ind: str, indent: int) -> list[str]:
    """Translate ``<MAP-CONTENTS (var container) body>`` as a ``for`` loop over contents."""
    if len(form) > 2 and isinstance(form[1], (list, tuple)):
        var_list = form[1]
        var_name = sanitize_ident(str(var_list[0])) if var_list else "item"
        from .identifiers import as_object  # local — only used here

        container = as_object(t._translate_expr(var_list[1])) if len(var_list) > 1 else "this"
        body = list(form[2:])
        inner = t._translate_body(body, indent + 1)
        return [f"{ind}for {var_name} in {container}.contents.all():"] + inner
    return [f"{ind}# ZIL: {form!r}  (MAP-CONTENTS not translated)"]


def _h_move(t: "ZilTranslator", form: list, ind: str, _indent: int) -> list[str]:
    """Translate ``<MOVE obj dest>`` as ``obj.moveto(dest)``."""
    obj = t._translate_expr(form[1]) if len(form) > 1 else "None"
    dest = t._translate_expr(form[2]) if len(form) > 2 else "None"
    return [f"{ind}{obj}.moveto({dest})"]


def _h_remove(t: "ZilTranslator", form: list, ind: str, _indent: int) -> list[str]:
    """Translate ``<REMOVE obj>`` (and ``<REMOVE-CAREFULLY>``) as ``_.remove(obj)``."""
    obj = t._translate_expr(form[1]) if len(form) > 1 else "None"
    return [f"{ind}_.remove({obj})"]


def _h_goto(t: "ZilTranslator", form: list, ind: str, _indent: int) -> list[str]:
    """Translate ``<GOTO room>`` as ``_.goto(room)``."""
    room = t._translate_expr(form[1]) if len(form) > 1 else "None"
    return [f"{ind}_.goto({room})"]


def _h_do_walk(t: "ZilTranslator", form: list, ind: str, _indent: int) -> list[str]:
    """Translate ``<DO-WALK direction>`` as ``_.walk(direction)``."""
    direction = t._translate_expr(form[1]) if len(form) > 1 else '"north"'
    return [f"{ind}_.walk({direction})"]


def _h_fset(t: "ZilTranslator", form: list, ind: str, _indent: int) -> list[str]:
    """Translate ``<FSET obj flag>`` as ``obj.set_flag(flag, True)``."""
    obj = t._translate_expr(form[1]) if len(form) > 1 else "None"
    flag = t._translate_flag_name(form[2]) if len(form) > 2 else '"unknown"'
    return [f"{ind}{obj}.set_flag({flag}, True)"]


def _h_fclear(t: "ZilTranslator", form: list, ind: str, _indent: int) -> list[str]:
    """Translate ``<FCLEAR obj flag>`` as ``obj.set_flag(flag, False)``."""
    obj = t._translate_expr(form[1]) if len(form) > 1 else "None"
    flag = t._translate_flag_name(form[2]) if len(form) > 2 else '"unknown"'
    return [f"{ind}{obj}.set_flag({flag}, False)"]


def _h_putp(t: "ZilTranslator", form: list, ind: str, _indent: int) -> list[str]:
    """Translate ``<PUTP obj prop val>`` as ``obj.set_property(prop, val)``."""
    from .identifiers import as_object, routine_dot_name

    obj = as_object(t._translate_expr(form[1])) if len(form) > 1 else "None"
    prop = t._translate_prop_name(form[2]) if len(form) > 2 else '"unknown"'
    # ``P?ACTION`` stores a ROUTINE REFERENCE, not a computed value.  ZIL
    # ``<PUTP obj P?ACTION ,DARK-FUNCTION>`` sets the object's action
    # handler to the routine itself; the runtime dispatches it later by
    # name (see ``dispatch_object_function`` / the player-action hook in
    # do_command).  Translating the routine atom through ``_translate_expr``
    # would emit a CALL (``_.thing.dark_function()``) and store its return
    # value — wrong.  Emit the routine's snake-name STRING instead so the
    # action property holds a dispatchable verb name.
    if len(form) > 3 and prop in ("'action'", '"action"') and isinstance(form[3], str):
        atom = form[3].lstrip(",.").upper()
        if atom in t.routine_atoms:
            name = routine_dot_name(atom) or atom.lower().replace("-", "_")
            return [f"{ind}{obj}.set_property({prop}, {name!r})"]
    val = t._translate_expr(form[3]) if len(form) > 3 else "None"
    return [f"{ind}{obj}.set_property({prop}, {val})"]


_PARSER_STATE_SLOTS = frozenset({"PRSA", "PRSO", "PRSI", "P-PRSA", "P-PRSO", "P-PRSI", "P-LEXV"})


def _h_setg(t: "ZilTranslator", form: list, ind: str, _indent: int) -> list[str]:
    """Translate ``<SETG key val>`` as ``context.player.zstate_set('key', val)``."""
    key = str(form[1]).upper() if len(form) > 1 else "UNKNOWN"
    # See explanation/zil-importer (Parser-state SETG is a no-op).
    if key in _PARSER_STATE_SLOTS:
        return [f"{ind}# SETG of parser-state slot is a no-op in DjangoMOO"]
    val = t._translate_expr(form[2]) if len(form) > 2 else "None"
    return [f"{ind}context.player.zstate_set({repr(key)}, {val})"]


def _h_score(t: "ZilTranslator", form: list, ind: str, _indent: int) -> list[str]:
    """Translate ``<SCORE delta>`` as ``_.score_update(delta)``."""
    delta = t._translate_expr(form[1]) if len(form) > 1 else "0"
    return [f"{ind}_.score_update({delta})"]


def _h_jigs_up(t: "ZilTranslator", form: list, ind: str, _indent: int) -> list[str]:
    """Translate ``<JIGS-UP msg>`` (death) as ``_.jigs_up(msg)``.

    The peephole in ``_fold_tell_into_jigs_up`` may wrap the msg arg in
    a synthetic ``<TELL ...>`` form when a TELL immediately preceded
    the JIGS-UP in the source body.  Detect that shape and use the
    TELL segment-string builder so the merged text becomes a single
    JIGS-UP call argument (and lands in jigs_up's print buffer rather
    than triggering a sub-verb buffer flush ordering issue).
    """
    if len(form) > 1:
        arg = form[1]
        if isinstance(arg, list) and arg and isinstance(arg[0], str) and arg[0].upper() == "TELL":
            msg = t._tell_string_expr(arg)
        else:
            msg = t._translate_expr(arg)
    else:
        msg = '""'
    return [f"{ind}_.jigs_up({msg})"]


def _h_quit(_t: "ZilTranslator", _form: list, ind: str, _indent: int) -> list[str]:
    """Translate ``<QUIT>`` as a goodbye message + bare ``return``."""
    return [f"{ind}print('Goodbye.')", f"{ind}return"]


def _h_restart(_t: "ZilTranslator", _form: list, ind: str, _indent: int) -> list[str]:
    """Translate ``<RESTART>`` as a notice — no Z-machine state to reset in DjangoMOO."""
    return [f"{ind}print('Restart not supported in DjangoMOO.')"]


def _h_save_restore(_t: "ZilTranslator", form: list, ind: str, _indent: int) -> list[str]:
    """Translate ``<SAVE>`` / ``<RESTORE>`` as a falsy stub (unsupported opcode)."""
    head = form[0].upper()
    return [f"{ind}False  # {head}: Z-machine save/restore not supported"]


def _emit_schedule(routine: str, delay_expr: str, ind: str) -> str:
    """Pick between native real-time scheduling and the per-player turn queue.

    Real-time daemons (:mod:`daemon_modes` allowlist) route through
    ``_.schedule_realtime("<snake>", delay)`` which wraps
    :func:`moo.sdk.invoke` with ``periodic=True``.  Turn-mode daemons
    stay on the existing ``_.queue("<kebab>", delay)`` per-player
    interrupt queue.

    The routine name is always passed as a string literal — never as a
    bare atom — so ``_translate_atom`` doesn't resolve it to a function
    call whose return value would land in the queue/registry as the
    "name".

    :param routine: Kebab-case ZIL routine atom (e.g. ``"i-thief"``).
    :param delay_expr: Already-translated Python expression for delay.
    :param ind: Indent string.
    :returns: A single Python statement line.
    """
    if daemon_modes.classify(routine) == "realtime":
        verb_name = routine.replace("-", "_")
        return f"{ind}_.schedule_realtime({verb_name!r}, {delay_expr})"
    return f"{ind}_.queue({routine!r}, {delay_expr})"


def _emit_unschedule(routine: str, ind: str) -> str:
    """Counterpart to :func:`_emit_schedule` — routes ``DISABLE`` by mode.

    :param routine: Kebab-case ZIL routine atom.
    :param ind: Indent string.
    :returns: A single Python statement line.
    """
    if daemon_modes.classify(routine) == "realtime":
        verb_name = routine.replace("-", "_")
        return f"{ind}_.unschedule_realtime({verb_name!r})"
    return f"{ind}_.cancel({routine!r})"


def _h_queue(t: "ZilTranslator", form: list, ind: str, _indent: int) -> list[str]:
    """Translate bare ``<QUEUE r delay>``.

    Routes to ``_.schedule_realtime`` for native-scheduler daemons (see
    :mod:`daemon_modes`) or ``_.queue`` for turn-mode daemons.  The
    routine atom must be passed as a string name (matching the daemon's
    snake-cased verb name) regardless of mode; otherwise
    ``_translate_atom`` resolves it to a function call
    (``_.thing.i_foo()``) which queues the daemon's return value
    (a bool) as the queue entry's name — later crashing
    ``queue.tick`` with ``AttributeError: 'bool' object has no attribute 'lower'``.
    """
    routine = str(form[1]).lower().replace("_", "-") if len(form) > 1 else "unknown"
    delay = t._translate_expr(form[2]) if len(form) > 2 else "1"
    return [_emit_schedule(routine, delay, ind)]


def _h_enable(t: "ZilTranslator", form: list, ind: str, _indent: int) -> list[str]:
    """Translate ``<ENABLE <QUEUE r delay>>`` / ``<ENABLE <INT r>>``.

    Dispatches through the same per-mode router as :func:`_h_queue`.
    The ``<INT r>`` form (re-enable a previously-disabled daemon) is
    emitted with delay ``0`` so it fires on the next turn / tick.
    """
    inner = form[1] if len(form) > 1 else None
    if isinstance(inner, list) and inner:
        inner_head = str(inner[0]).upper()
        if inner_head == "QUEUE":
            routine = str(inner[1]).lower().replace("_", "-") if len(inner) > 1 else "unknown"
            delay = t._translate_expr(inner[2]) if len(inner) > 2 else "1"
            return [_emit_schedule(routine, delay, ind)]
        if inner_head == "INT":
            routine = str(inner[1]).lower().replace("_", "-") if len(inner) > 1 else "unknown"
            return [_emit_schedule(routine, "0", ind)]
    return [f"{ind}# ZIL: {form!r}  (ENABLE not translated)"]


def _h_disable(_t: "ZilTranslator", form: list, ind: str, _indent: int) -> list[str]:
    """Translate ``<DISABLE <INT r>>`` via the per-mode router."""
    inner = form[1] if len(form) > 1 else None
    if isinstance(inner, list):
        routine = str(inner[1]).lower().replace("_", "-") if len(inner) > 1 else "unknown"
        return [_emit_unschedule(routine, ind)]
    return [f"{ind}# ZIL: {form!r}  (DISABLE not translated)"]


def _h_perform(t: "ZilTranslator", form: list, ind: str, _indent: int) -> list[str]:
    """Translate ``<PERFORM verb prso prsi>`` as ``_.perform(verb, prso, prsi)``."""
    verb_atom = t._translate_expr(form[1]) if len(form) > 1 else '"unknown"'
    prso = t._translate_expr(form[2]) if len(form) > 2 else "None"
    prsi = t._translate_expr(form[3]) if len(form) > 3 else "None"
    return [f"{ind}_.perform({verb_atom}, {prso}, {prsi})"]


def _h_set(t: "ZilTranslator", form: list, ind: str, _indent: int) -> list[str]:
    """Translate ``<SET var val>`` (statement) as a Python assignment."""
    var = sanitize_ident(str(form[1])) if len(form) > 1 else "v_unknown"
    val = t._translate_expr(form[2]) if len(form) > 2 else "None"
    return [f"{ind}{var} = {val}"]


def _h_dumb_container(_t: "ZilTranslator", _form: list, ind: str, _indent: int) -> list[str]:
    """Translate ``<DUMB-CONTAINER>`` as the canonical open/close/examine stub."""
    return [
        f'{ind}if verb_name in ["open", "close", "shut", "look-inside"]:',
        f'{ind}    print("You can\'t do that.")',
        f"{ind}    return",
        f'{ind}elif verb_name in ["examine", "x", "describe", "what"]:',
        f'{ind}    print("It looks pretty much like a " + context.parser.get_dobj().desc() + ".")',
        f"{ind}    return",
    ]


def _h_article(t: "ZilTranslator", form: list, ind: str, _indent: int) -> list[str]:
    """Translate ``<ARTICLE obj the>`` as ``print(article(obj, the), end='')``.

    ZIL's ARTICLE is semantically a TELL — prints the object's article
    plus desc inline as part of a TELL chain.  The hand-written
    ``verbs/thing/helpers/article.py`` returns the string instead
    of printing, so we emit a ``print(..., end='')`` that lands the
    article in the caller's print buffer rather than triggering a
    sub-verb buffer flush.  This fixes the "article-text-first,
    parent-text-last" interleaving that broke ``put X in Y`` and the
    bulldozer death message.
    """
    from .identifiers import substrate_receiver  # pylint: disable=import-outside-toplevel

    obj_expr = t._translate_expr(form[1]) if len(form) > 1 else "None"
    the_expr = t._translate_expr(form[2]) if len(form) > 2 else "False"
    receiver = substrate_receiver("article")
    return [f"{ind}print({receiver}.article({obj_expr}, {the_expr}), end='')"]


def _h_default(t: "ZilTranslator", form: list, ind: str, _indent: int) -> list[str]:
    """
    Fallback handler — translate as an expression statement.

    Unhandled non-SDK heads also get a ``# ZIL: <head ...>`` debug
    annotation so the original form is greppable in the output.
    """
    from .constants import SDK_HEADS

    expr = t._translate_expr(form)
    if expr == "None" and isinstance(form, list):
        comment = repr(form)[:120]
        return [f"{ind}# ZIL: {comment}", f"{ind}pass"]
    if isinstance(form, list) and form and isinstance(form[0], str):
        head_atom = form[0].upper()
        if head_atom not in SDK_HEADS and head_atom[0].isalpha() and not head_atom.startswith("V?"):
            return [f"{ind}# ZIL: <{form[0]} ...>", f"{ind}{expr}"]
    return [f"{ind}{expr}"]


HANDLERS: dict[str, Handler] = {
    "RTRUE": _h_rtrue,
    "RFALSE": _h_rfalse,
    "RFATAL": _h_rfatal,
    "RETURN": _h_return,
    "TELL": _h_tell,
    "CRLF": _h_crlf,
    "PRINT": _h_print,
    "PRINTI": _h_printi,
    "PRINT-CR": _h_print_cr,
    "PRINTR": _h_print_cr,
    "PRINTN": _h_printn,
    "PRINTB": _h_printn,  # PRINTB has identical statement-form translation
    "PRINTC": _h_printc,
    "PRINTD": _h_printd,
    "PRINT-CONTENTS": _h_print_contents,
    "APPLY": _h_apply,
    "COND": _h_cond,
    "AND": _h_and,
    "OR": _h_or,
    "NOT": _h_not,
    "REPEAT": _h_repeat,
    "PROG": _h_prog,
    "MAP-CONTENTS": _h_map_contents,
    "MOVE": _h_move,
    "REMOVE": _h_remove,
    "REMOVE-CAREFULLY": _h_remove,
    "GOTO": _h_goto,
    "DO-WALK": _h_do_walk,
    "FSET": _h_fset,
    "FCLEAR": _h_fclear,
    "PUTP": _h_putp,
    "SETG": _h_setg,
    "SCORE": _h_score,
    "JIGS-UP": _h_jigs_up,
    "QUIT": _h_quit,
    "RESTART": _h_restart,
    "RESTORE": _h_save_restore,
    "SAVE": _h_save_restore,
    "ENABLE": _h_enable,
    "QUEUE": _h_queue,
    "DISABLE": _h_disable,
    "PERFORM": _h_perform,
    "SET": _h_set,
    "DUMB-CONTAINER": _h_dumb_container,
    "ARTICLE": _h_article,
}
