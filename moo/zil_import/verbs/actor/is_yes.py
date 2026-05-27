#!moo verb is_yes --on "Actor"
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Stand-in for the canonical Zork YES? predicate.

The ZIL YES? routine reads a fresh line of input and tests its first
character for 'Y'.  DjangoMOO has no synchronous re-prompt path from
inside a verb (verb dispatch is single-shot), so we always answer
``True``.  This collapses the quit/restart confirmation flow into a
one-step yes, which matches how multi-user MUDs handle these commands.

If a future enhancement needs interactive confirmation, the right
mechanism is a temporary state on the player object plus a follow-up
verb that consults it.
"""

return True
