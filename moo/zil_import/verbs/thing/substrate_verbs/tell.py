#!moo verb tell addres --on "Thing" --dspec this
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Hand-written V-TELL replacement.

The auto-translated body fires HHG's ``,P-CONT`` continuation branch
(``<SETG WINNER ,PRSO>``) whenever an actor is the dobj — but DjangoMOO
doesn't carry intra-line continuations the way the Z-machine did, so
that branch always returned silently.  Player-visible effect:
``talk to barman`` produced empty output.

This override prints the canonical "Hmmm... looks at you expectantly"
line for actor dobjs (skipping the continuation special case entirely)
and the "You can't talk to X!" rebuke otherwise — matching the V-TELL
fallthrough that the original ZIL falls into when no continuation is
present.
"""

from moo.sdk import NoSuchObjectError, context

parser = context.parser
try:
    prso = parser.get_dobj() if parser.has_dobj_str() else None
except NoSuchObjectError:
    prso = None

if prso is None:
    if parser is not None and parser.has_dobj_str():
        print("There is no '" + parser.dobj_str + "' here.")
    else:
        print("What do you want to tell?")
    return

if prso.flag("actorbit"):
    print("Hmmm ..." + _.thing.article(prso, True) + " looks at you expectantly, as if you seemed to be about to talk.")
    return

print("You can't talk to" + _.thing.article(prso) + "!")
