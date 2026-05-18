#!moo verb recycle --on "Zork Actor NPC"
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Called by :func:`Object.delete` just before this NPC is removed.

Drops the anonymous ``Player`` row associated with this avatar. Real
user-tied Player rows (if any) are left alone — the SDK helper checks
``user=None`` before deleting.
"""

from moo.sdk import remove_player_record

remove_player_record(this)
