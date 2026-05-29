#!moo verb clocker --on $thing
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
ZIL CLOCKER replacement (HHG variant — canonical early break).

The original ZIL CLOCKER walks the C-TABLE / C-INTS / C-DEMONS Z-machine
data structures we don't translate.  Our equivalent lives in
``zil_sdk/queue_sdk.py:tick`` which processes the per-player
``zstate_queue`` and fires due daemons.

Return ``tick``'s significant-event flag (True when a due daemon fired
and its routine returned truthy — ZIL's "I did something this turn"
signal).  Canonical CLOCKER returns T on such events, and V-WAIT breaks
its loop the moment CLOCKER returns T — so ``wait`` stops as soon as
something happens (e.g. the Vogon fleet arrives at the Country Lane)
instead of blindly burning all 3 turns past the player's reaction
window.  Without this, the Earth-escape hitchhike is unwinnable: a
single ``wait`` advances VOGON-COUNTER 0→3, leaving no room to
``take thumb`` (→4) and ``push green button`` (→5 = JIGS-UP "Earth
destroyed").

zork1 uses the non-breaking variant (``verbs/zork1/...``) because its
smoke sequence hand-counts ``wait`` ticks for the river/reservoir/candle
cadence.
"""

return _.tick()
