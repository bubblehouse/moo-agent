#!moo verb initialize --on "Zork Actor NPC"
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Called by the M2M post_add signal handler after a Zork NPC's parents
are wired up (and previously by ``moo.sdk.create`` directly).

Two responsibilities:

1. Ensure an anonymous ``Player`` row exists for this avatar so the
   parser treats the NPC as a player target (``is_player() == True``)
   while ``is_connected()`` stays ``False`` — ``tell()`` drops silently
   rather than raising.  Mirrors the default-bootstrap ``$npc`` hook.

2. Grant ``everyone`` move + write on the NPC so daemons that mutate
   NPC state (thief flags, etc.) work under the non-wizard Adventurer
   avatar.  ``passthrough()`` chains through to ``Zork Thing/initialize``
   (via Zork Actor NPC → Zork Actor → Zork Thing) which grants both
   ``move`` and ``write``.
"""

from moo.sdk import ensure_player_record

ensure_player_record(this)
passthrough()  # → Zork Thing/initialize: move + write
