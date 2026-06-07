#!moo verb clocker --on $thing
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
ZIL CLOCKER replacement (beyondzork variant — no early break).

The original ZIL CLOCKER walks the C-TABLE / C-INTS / C-DEMONS Z-machine
data structures the importer doesn't translate.  Our equivalent lives in
``zil_sdk/queue_sdk.py:tick`` which processes the per-player ``zstate_queue``
and fires due daemons.

Whenever translated ZIL code calls ``clocker`` (e.g. V-WAIT loops it to
advance N turns), forward to ``tick`` so the same daemons fire.  Without this
shim ``wait`` crashed: ``#NNN (Thing) has no attribute 'clocker'``.

Returns False so V-WAIT's ``while`` loop runs to completion (all N turns).
Mirrors the zork1/zork3 no-early-break variant; if a future shakedown surfaces
a timed Beyond Zork puzzle with a narrow reaction window, switch to the
early-breaking variant (return ``tick``'s significant-event flag) as HHG does.
"""

_.tick()
return False
