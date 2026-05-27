#!moo verb go_next --on "Thing" --dspec this
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Canonical ZIL GO-NEXT (actions.zil):

    <ROUTINE GO-NEXT (TBL "AUX" VAL)
      <COND (<SET VAL <LKP ,HERE .TBL>>
             <COND (<NOT <GOTO .VAL>> 2)
                   (T 1)>)>>

Returns 0 (falsy) if the player's current room is not in the table; 1 if
GOTO succeeds; 2 if GOTO refuses the move.  The auto-translator drops the
trailing literal-constant clause bodies (1 and 2) as "pointless statements"
because COND is in statement context — it can't tell that this routine's
last form IS its return value.  Hand-rolling the dispatcher closes the
RIVER-LAUNCH gap (and any future GO-NEXT consumer that needs the 1-vs-2
distinction).
"""

from moo.sdk import context

tbl = args[0] if args else None
val = _.thing.lkp(context.player.here(), tbl)
if not val:
    return 0
if not _.thing.goto(val):
    return 2
return 1
