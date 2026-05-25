#!moo verb clocker --on $thing
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
ZIL CLOCKER replacement.

The original ZIL CLOCKER walks the C-TABLE / C-INTS / C-DEMONS Z-machine
data structures we don't translate.  Our equivalent lives in
``zil_sdk/queue_sdk.py:tick`` which processes the per-player
``zstate_queue`` and fires due daemons.

Whenever translated ZIL code calls ``clocker`` (e.g. V-WAIT loops it
to advance N turns), forward to ``tick`` so the same daemons fire.
Returns False so V-WAIT's ``while`` loop runs to completion (the
original CLOCKER returns True only on early termination via WON-GAME
or similar — none of which apply here).
"""

_.tick()
return False
