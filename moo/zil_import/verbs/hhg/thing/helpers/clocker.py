#!moo verb clocker --on $thing
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
ZIL CLOCKER replacement (HHG variant — single tick per turn).

The original ZIL CLOCKER walks the C-TABLE / C-INTS / C-DEMONS Z-machine
data structures we don't translate.  Our equivalent lives in
``verbs/system/queue.py:tick`` which processes the per-player
``zstate_queue`` and fires due daemons.

**Why this is a no-op.**  ``do_command`` already calls ``_.tick()`` once
at the top of *every* command — that single tick is this turn's CLOCKER
(it fires the due daemons and advances every turn-counter by one).
``clocker`` is invoked only by V-WAIT, which loops it to "pass time."
If it ticked again, a ``wait`` would advance daemons TWICE per turn
(do_command's pre-tick + V-WAIT's clock) while every other command
advances them once — an inconsistent +2 step.

That +2 is fatal to HHG's Vogon act, one long daemon cascade gated on
exact-equality counters: I-CAPTAIN reads the poetry and at CAPTAIN-COUNTER
``== 6`` has the guards toss you out; I-FORD stalls the guard and at
GUARDS-COUNTER ``== 6`` throws you in the airlock; AIRLOCK-F at
AIRLOCK-COUNTER ``== 4`` blows you into space and the Heart of Gold scoops
you up.  Stepping +2 makes whether a gate value lands on a tick boundary
depend on the parity of when the daemon armed — a wrong-parity start steps
straight over ``== 6``, the gate never fires, the daemon is never DISABLEd,
and the counter runs away (observed: 56, 176) while the player oscillates
back into the chair.  Stepping +1 hits every integer, so every gate fires
regardless of when its daemon started.

Returning False (rather than ticking) also means V-WAIT never breaks
early — but it no longer needs to: a ``wait`` is now exactly one turn
(do_command's tick), so there is no multi-turn window to break out of.
This also gives the Earth-escape hitchhike maximum control (the fleet's
VOGON-COUNTER advances one per ``wait``, leaving ample room to ``take
thumb`` and ``push green button`` before the demolition).

zork1 keeps the ticking variant (``verbs/zork1/...``) because its smoke
hand-counts ``wait`` as a fixed multi-tick cadence (i-river drift /
i-rempty reservoir-drain / i-candles burn); that game has no
exact-counter daemon gate that the +2 step would skip.
"""

return False
