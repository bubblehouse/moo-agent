#!moo verb act --on "Actor NPC"
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Personality hook for a Zork NPC. The base implementation is a no-op —
NPC subclasses override this verb (e.g. the thief's patrol logic, the
cyclops's rage update) to decide whether to move, speak, attack, or
idle when the daemon fires.

For NPCs with a corresponding ``I-<NAME>`` ZIL daemon, the translator
emits the routine body as an override of this verb on the per-NPC
directory (``verbs/rooms/<room>/<actor>/act.py``).  NPCs without a
daemon inherit this stub and stay command-driven.

Modeled after the default-bootstrap ``$npc.act`` verb.
"""

return None
