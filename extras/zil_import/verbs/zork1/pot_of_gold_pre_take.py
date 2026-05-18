#!moo verb pre_take --on "pot of gold" --dspec this
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Gate the pot of gold's take action on the rainbow-flag (set when the
player waves the sceptre to solidify the rainbow).  Canonical Zork I
hides the pot at End of Rainbow until then.

Returning truthy short-circuits the substrate take and prints the
canonical block message.  Returning False/None lets take proceed.
"""

from moo.sdk import context

if not context.player.zstate_get("RAINBOW-FLAG"):
    print("There's no way to reach it.")
    return True
return False
