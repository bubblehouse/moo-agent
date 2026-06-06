#!moo verb diagnose --on "Actor" --dspec none
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Hand-written V-DIAGNOSE replacement (zork3 variant).

The translator drops V-DIAGNOSE (it's in the global ``_SKIP_ROUTINES``
set, carried over because zork1's V-DIAGNOSE needs a hand-written body).
zork3's V-DIAGNOSE is unrelated to zork1's C-TABLE health math — it is a
single table lookup:

    <ROUTINE V-DIAGNOSE () <TELL <GET ,DIAG ,P-STRENGTH> CR>>

``DIAG`` is the 6-entry string table loaded onto the System Object as
``zstate_diag`` (index 0 = "You are dead." … 5 = "You are in perfect
health.").  ``P-STRENGTH`` lives in player zstate and opens at 5.
"""

from moo.sdk import context

player = context.player
strength = player.zstate_get("P-STRENGTH")
if strength is None:
    strength = 5
message = _.table_get(_.get_property("zstate_diag"), strength)
if message is not None:
    print(message)
