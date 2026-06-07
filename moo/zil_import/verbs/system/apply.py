#!moo verb apply --on "System Object"
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""ZIL ``<APPLY routine-value [m-const]>`` — dynamic routine dispatch.

Beyond Zork applies a stored ROOM/OBJECT action routine with an M-* lifecycle
constant, in two shapes the inline ``_h_apply`` translator handler can't catch
because the routine arrives through a *variable*::

    <SET X <GETP ,HERE ,P?ACTION>>
    <APPLY .X ,M-LOOK>          ; describe the current room
    <APPLY <GETP ,HERE ,P?ACTION> ,M-ENTERING>

Two dispatch shapes:

1. **M-* lifecycle dispatch** — ``<APPLY …action… ,M-LOOK>``: the routine value
   is an ``action`` property and ``args[1]`` is an M-* constant.  We dispatch the
   corresponding role verb on the current room (``context.player.location``);
   every such site in the look / move / enter paths is HERE-relative.

2. **General routine-value dispatch** — ``<APPLY ,MAP-ROUTINE ,HERE ,MAPY ,MAPX>``:
   the routine value is a Thing-routine *name* (the XZIP routine-value
   translation emits the name string), invoked with the remaining args.  Used by
   the auto-map (``MAP-ROUTINE`` → ``close_map``) and the stats line
   (``STAT-ROUTINE`` → ``rawbar``).

Returns ``None`` for an unresolvable routine so the caller proceeds — Python 3
has no ``apply`` builtin, so without this the translated call would ``NameError``.
"""

from moo.sdk import context

fcn = args[0] if len(args) > 0 else None
rest = list(args[1:])

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

# Shape 1: M-* lifecycle dispatch on the current room.
m_const = rest[0] if rest else None
verb_to_call = m_to_verb.get(m_const) if isinstance(m_const, str) else None
if verb_to_call is not None:
    receiver = context.player.location
    # recurse=False so an inheriting substrate's role verb can't loop forever.
    if receiver is None or not receiver.has_verb(verb_to_call, recurse=False):
        return None
    return receiver.invoke_verb(verb_to_call, m_const)

# Shape 2: general routine-value dispatch — fcn is a Thing-routine name.
if isinstance(fcn, str):
    thing = _.get_property("thing")
    if thing is not None and thing.has_verb(fcn, recurse=False):
        return thing.invoke_verb(fcn, *rest)
return None
