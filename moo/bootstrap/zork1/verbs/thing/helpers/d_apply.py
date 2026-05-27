#!moo verb d_apply --on "Thing" --dspec none
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Hand-written replacement for ZIL's ``<APPLY .FCN .FOO>`` form.

The translator-emitted body calls Python 2's ``apply()`` builtin, which
doesn't exist in Python 3 and crashes the moment the function pointer
chain in :verb:`perform` (and now ``do_command``) is activated.

ZIL invokes APPLY on three kinds of function pointers:

- ``loc.action`` for M-Beg / M-End (the ROOM-FUNCTION atom)
- ``obj.action`` for PRSI / PRSO action stages (OBJECT-FUNCTION atom)
- Table-resolved ``ACTIONS``/``PREACTIONS`` entries (table call)

This shim handles the first two — the table-call path is dormant in the
current emission (Preaction / Default stages never resolve a non-None
table entry).  Receiver inference is by perform's stage label so the
existing :verb:`perform` call sites don't need to change.

Call shapes (matching ``verbs/thing/helpers/perform.py``)::

    _.thing.d_apply("M-Beg",     loc_action, "M-BEG")
    _.thing.d_apply("Preaction", preact)            # currently no-op
    _.thing.d_apply("PRSI",      i_action)
    _.thing.d_apply("PRSO",      o_action)
    _.thing.d_apply(False,       default)           # currently no-op

For the M-Beg path, the action atom names the **ROOM-FUNCTION routine**
(e.g. ``"forest_room"``).  Until Phase 7d collapses per-M-clause files,
the actual handler is split across per-clause verbs whose names are the
M-constant role (``preturnfunc`` for M-BEG, ``turnfunc`` for M-END, …).
``M_TO_VERB`` maps the constant to the role name so the dispatch lands
on the existing file.

For PRSI / PRSO, the action atom is the OBJECT-FUNCTION routine name
(snake_case).  Under the current emission, OBJECT-FUNCTIONs are split
into per-VERB? files at the object's directory — there is no single
verb named after the atom.  The parser already invokes the right
per-VERB? file as part of normal dispatch, so PRSI/PRSO d_apply here
is intentionally a no-op until Phase 7d emits collapsed callbacks.
"""

from moo.sdk import context

stage = args[0] if len(args) > 0 else None
fcn = args[1] if len(args) > 1 else None
m_const = args[2] if len(args) > 2 else None

if not fcn:
    return None

M_TO_VERB = {
    "M-BEG": "preturnfunc",
    "M-END": "turnfunc",
    "M-ENTER": "enterfunc",
    "M-LEAVE": "exitfunc",
    "M-FLASH": "flashfunc",
    "M-OBJDESC": "descfunc",
    "M-LOOK": "look",
}

if stage == "M-Beg":
    receiver = context.player.location
    verb_to_call = M_TO_VERB.get(m_const)
    if receiver is None or verb_to_call is None:
        return None
    if not receiver.has_verb(verb_to_call):
        return None
    return receiver.invoke_verb(verb_to_call, m_const)

return None
