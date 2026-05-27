#!moo verb d_apply --on "Thing" --dspec none
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
M-Beg lifecycle router for ROOM-FUNCTION callbacks.

Hand-written replacement for ZIL's ``<APPLY .FCN .FOO>`` form — the
translator-emitted body would call Python 2's ``apply()`` builtin
(removed in Python 3).

Active path
-----------
Only the ``"M-Beg"`` stage does real work.  The action atom names a
ROOM-FUNCTION routine (e.g. ``"forest_room"``).  ``M_TO_VERB`` maps the
M-constant to the role-name verb (``preturnfunc`` for M-BEG, ``turnfunc``
for M-END, …) that the combined-clause emitter registers on the room.

Call shape::

    _.thing.d_apply("M-Beg", loc_action, "M-BEG")

Other stages
------------
:verb:`perform` still calls d_apply for the Preaction (Stage 2) and
Default/table (Stage 5) stages, but both fall through to ``return None``
here because the translator currently emits no Preaction or Default
callable — the chain proceeds to the next stage.  PRSI and PRSO are
bypassed entirely: :verb:`perform` routes those through
:verb:`dispatch_object_function`, which looks up ``obj.action`` and
invokes the combined OBJECT-FUNCTION callback.
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
