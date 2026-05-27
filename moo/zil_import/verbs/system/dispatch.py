#!moo verb run_v_routine --on "System Object"
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
ZIL ACTION → V-routine fall-through.

ZIL semantics: an object's ACTION routine runs first.  If it returns FALSE
(no print, no early return), the standard ``V-<verb>`` runs.  In Python the
per-object routine just falls off the end without an explicit ``return``;
this helper picks up where it left off and invokes the matching ``V-*``
verb on ``$thing``.

:param args[0]: The player verb the action was dispatched for.
:param args[1]: Optional dobj override (defaults to ``context.parser.get_dobj()``).
"""

from moo.sdk import context, NoSuchObjectError

verb_name_arg = args[0] if args else None
if not verb_name_arg:
    return

# QUARANTINE (Phase 1): ZIL's V-WALK uses Z-machine exit-table opcodes
# (getpt/ptsize/UEXIT/NEXIT/...) that have no Python equivalent.  Until
# Phase 3 lands a verb-driven exit model, route movement verbs through the
# generic walk() helper instead of falling through to the broken substrate.
WALK_VERBS = {"walk", "go", "move", "run", "proceed", "step"}
if verb_name_arg in WALK_VERBS:
    parser = context.parser
    direction = None
    if parser.has_dobj_str():
        direction = parser.get_dobj_str()
    elif len(parser.words) > 1:
        direction = parser.words[1]
    if direction:
        _.walk(direction)
    return

# After Phase 3 item 3, substrate verbs are registered without the
# ``v-`` prefix.  Look up by plain name on $thing.
thing = _.get_property("thing")
if thing is None or not thing.has_verb(verb_name_arg):
    # No standard substrate routine for this verb; nothing to fall through to.
    return

thing.invoke_verb(verb_name_arg)
