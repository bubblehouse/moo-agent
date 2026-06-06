#!moo verb apply --on "System Object"
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""ZIL ``<APPLY routine-value [m-const]>`` — dynamic routine dispatch.

Beyond Zork applies a stored ROOM/OBJECT action routine with an M-* lifecycle
constant, in two shapes the inline ``_h_apply`` translator handler can't catch
because the routine arrives through a *variable*::

    <SET X <GETP ,HERE ,P?ACTION>>
    <APPLY .X ,M-LOOK>          ; describe the current room
    <APPLY <GETP ,HERE ,P?ACTION> ,M-ENTERING>

The routine value is an ``action`` property (a routine name); the M-* constant
selects the role verb the combined-clause emitter registered on the room.  We
dispatch that verb on the current room (``context.player.location``) — every
``<APPLY …action… M-*>`` site in the look / move / enter paths is HERE-relative.

General routine-value application (no M-constant, or a non-room receiver) is not
modelled and returns ``None`` so the caller proceeds — Python 3 has no ``apply``
builtin, so without this the translated call would ``NameError``.
"""

from moo.sdk import context

fcn = args[0] if len(args) > 0 else None
m_const = args[1] if len(args) > 1 else None

# M-* lifecycle constant -> role verb name (matches the generator's
# combined-clause filename split and translator/constants.py M_TO_VERB).
m_to_verb = {
    "M-LOOK": "look",
    "M-BEG": "preturnfunc",
    "M-END": "turnfunc",
    "M-ENTER": "enterfunc",
    "M-ENTERING": "enterfunc",
    "M-ENTERED": "enterfunc",
    "M-LEAVE": "exitfunc",
    "M-EXIT": "exitfunc",
    "M-FLASH": "flashfunc",
    "M-OBJDESC": "descfunc",
}

if not fcn:
    return None
verb_to_call = m_to_verb.get(m_const) if isinstance(m_const, str) else None
if verb_to_call is None:
    return None
receiver = context.player.location
# recurse=False so an inheriting substrate's role verb can't loop forever.
if receiver is None or not receiver.has_verb(verb_to_call, recurse=False):
    return None
return receiver.invoke_verb(verb_to_call, m_const)
