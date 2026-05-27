#!moo verb pre_sgive --on "Thing" --dspec this
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Hand-written PRE-SGIVE replacement.

The auto-translator emits ``_.perform("give", prsi, prso)`` unconditionally,
flipping parser dobj/iobj.  That works for the V-SGIVE form (``feed troll
axe``: dobj=troll iobj=axe) but BREAKS the V-GIVE form (``give axe to
troll``: dobj=axe iobj=troll already) because the flip yields dobj=troll
iobj=axe — the recipient's god-verb body checks ``prsi == this`` and the
swap puts the gift in prsi, missing the dispatch.

When the body misses, the god-verb falls through to ``passthrough()``,
which routes back to the actor-class give dispatcher → V-SGIVE → here →
``_.perform("give", ...)`` → recursion.

Detection rule: the canonical V-GIVE syntax uses ``to`` as the
preposition.  When ``to`` is present in parser.prepositions, the player
typed the ``give X to Y`` form and parser dobj/iobj already match the
recipient-as-PRSI convention the actor's god-verb expects — invoke the
actor's handler directly without swapping.

When ``to`` is absent (``feed troll axe`` or bare ``give troll axe``),
flip parser dobj/iobj so the actor handler sees prso=gift prsi=actor.

Either way, invoke the recipient's verb directly (not via ``_.perform``)
so a body that hits the passthrough fallback returns through this verb's
own ``return`` rather than re-entering the dispatcher.
"""

from moo.sdk import NoSuchObjectError, context

parser = context.parser
player = context.player

try:
    prso = parser.get_dobj() if parser.has_dobj_str() else None
except NoSuchObjectError:
    prso = None
try:
    prsi = parser.get_iobj() if parser.has_iobj() else None
except NoSuchObjectError:
    prsi = None

if prso is None:
    if parser is not None and parser.has_dobj_str():
        print("There is no '" + parser.dobj_str + "' here.")
    else:
        print("I don't know how to do that.")
    return True

if prsi == player or prso == player:
    print("You can't give something to yourself.")
    return True

# Determine which side is the actor / recipient.
v_give_form = bool(parser.prepositions and "to" in parser.prepositions)

if v_give_form:
    actor = prsi if prsi is not None and prsi.flag("actorbit") else None
    gift = prso
else:
    actor = prso if prso is not None and prso.flag("actorbit") else None
    gift = prsi
    if actor is not None and gift is not None:
        # V-SGIVE: swap parser so actor handler sees prso=gift, prsi=actor.
        parser.dobj = gift
        parser.dobj_str = gift.name if gift.name else parser.dobj_str
        try:
            parser.iobj = actor
        except AttributeError:
            pass

if actor is None:
    # No actor recipient — print the canonical "give to non-actor" refusal
    # rather than letting the substrate's "Foo!" fallback fire.
    if gift is not None and prsi is not None and prsi != gift:
        print("You can't give " + gift.desc() + " to " + prsi.desc() + ".")
    elif gift is not None:
        print("Give " + gift.desc() + " to whom?")
    else:
        print("Give what to whom?")
    return True

if gift is None:
    print("Give what to whom?")
    return True

# Invoke the recipient's give handler directly.  Skip the actor-class
# dispatcher (which would just call sgive again and recurse).  Pass no
# args so god-verb ``mode = args[0]`` stays None and the player-command
# branches run.
if actor.has_verb("give"):
    actor.invoke_verb("give")
else:
    print("The " + actor.desc() + " refuses it politely.")
return True
