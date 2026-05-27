#!moo verb attack fight hurt injure hit kill murder slay dispatch stab cut slice --on "Thing" --dspec this
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Hand-written V-ATTACK replacement.

Adds a self-reference branch: ``attack me`` / ``kill me`` / ``attack me
with sword`` shouldn't leak the SSH username via ``self.desc()``.  The
canonical Zork text uses "yourself" framing instead.

For non-self dobjs the body mirrors the auto-translated cascade
(non-actor refusal, hands refusal, weapon-not-held, non-weapon, then
HERO-BLOW dispatch).
"""

from moo.sdk import NoSuchObjectError, context, lookup

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
        print("What do you want to attack?")
    return

# Self-attack: canonical Zork refuses without revealing the player name.
# Mirrors CRETIN-FCN's attack branch: with weapon → death; without → refusal.
if prso == player:
    if prsi is not None and prsi.flag("weapon"):
        return _.jigs_up("If you insist.... Poof, you're dead!")
    print("Trying to attack yourself is a sign of psychic distress.")
    return

if not prso.flag("actorbit"):
    print("I've known strange people, but fighting a " + prso.desc() + "?")
    return
if prsi is None or prsi == lookup("hands"):
    print("Trying to attack a " + prso.desc() + " with your bare hands is suicidal.")
    return
if prsi.location != player:
    print("You aren't even holding the " + prsi.desc() + ".")
    return
if not prsi.flag("weapon"):
    print("Trying to attack the " + prso.desc() + " with a " + prsi.desc() + " is suicidal.")
    return
# ZIL: <HERO-BLOW ...>
return _.thing.hero_blow()
