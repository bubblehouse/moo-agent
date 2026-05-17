#!moo verb initialize --on "Zork Actor NPC"
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Called by :func:`moo.sdk.create` after a Zork NPC is created.

Ensures an anonymous ``Player`` row exists for this avatar so the parser
treats the NPC as a player target (``is_player() == True``) while
``is_connected()`` stays ``False`` — ``tell()`` drops silently rather
than raising.

Mirrors the default-bootstrap ``$npc`` initialize hook so any future
``@npc create``-style wizard tooling can rely on the same shape.
"""

from moo.sdk import ensure_player_record

ensure_player_record(this)
