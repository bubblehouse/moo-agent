#!moo verb clocker --on $thing
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
ZIL CLOCKER replacement (zork1 variant — no early break).

The original ZIL CLOCKER walks the C-TABLE / C-INTS / C-DEMONS Z-machine
data structures we don't translate.  Our equivalent lives in
``zil_sdk/queue_sdk.py:tick`` which processes the per-player
``zstate_queue`` and fires due daemons.

Whenever translated ZIL code calls ``clocker`` (e.g. V-WAIT loops it
to advance N turns), forward to ``tick`` so the same daemons fire.

Returns False so V-WAIT's ``while`` loop runs to completion (all N
turns).  zork1's canonical smoke sequence hand-counts ``wait`` as a
fixed number of ticks per command (the i-river drift / i-rempty
reservoir-drain / i-candles burn cadence the harness asserts on), so
this variant deliberately does NOT honour ``tick``'s significant-event
flag.  HHG uses the early-breaking variant (``verbs/hhg/...``) because
its Earth-escape hitchhike has a 3-turn reaction window that a
full-length ``wait`` would blow past.
"""

_.tick()
return False
