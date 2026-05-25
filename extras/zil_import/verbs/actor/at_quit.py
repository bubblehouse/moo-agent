#!moo verb @quit --on "Actor"
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
@quit: Disconnect from the MOO server.

The translated ZIL ``quit`` / ``q`` verb (V-QUIT) prompts for a yes/no
confirmation but doesn't actually disconnect the player — it just
returns to the read loop.  ``@quit`` is the canonical DjangoMOO
disconnect command (mirrors ``$player.@quit`` from the default
bootstrap) and actually severs the SSH session via ``boot_player``.

Players who type ``quit`` still hit V-QUIT for the canonical Zork
prompt; ``@quit`` is the unambiguous "I really mean leave" form.
"""

from moo.sdk import boot_player, context

print(f"Goodbye, {context.player.name}.")
boot_player(context.player)
