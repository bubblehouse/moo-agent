#!moo verb is_running --on "Thing" --dspec this
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
RUNNING? — is a daemon currently scheduled?

Canonical ZIL ``RUNNING?`` walks the ``C-TABLE`` clock-interrupt table,
but DjangoMOO schedules daemons via the per-player ``zstate_queue``
(``verbs/system/queue.py``) for turn-mode daemons and a System Object
``_realtime_pts`` registry for native/realtime daemons — and the
``C-TABLE`` globals are never populated.  So the auto-translated routine
always returned False, which silently killed every ``RUNNING?``-gated
branch (notably the improbability-drive win in ``SWITCH-F``:
``<RUNNING? ,I-TEA>`` + ``TEA-COUNTER > 6``).  This override checks the
real scheduler state instead.

The translator's ``RUNNING?`` handler passes the daemon's kebab-case
NAME string (``_.thing.is_running('i-tea')``) — NOT a call to the daemon
(the default emission ``is_running(_.thing.i_tea())`` would execute the
daemon as a side effect on every check).

:param args[0]: daemon name (e.g. ``"i-tea"``); hyphens or underscores ok.
:returns: True if the named daemon is currently scheduled.
"""

from moo.sdk import context, NoSuchPropertyError

name = args[0] if args else None
if name is None:
    return False
kebab = str(name).lower().replace("_", "-")
snake = kebab.replace("-", "_")

# Turn-mode daemons: per-player zstate_queue (list of {name, fire_at_turn, ...}).
try:
    queue = context.player.get_property("zstate_queue")
except NoSuchPropertyError:
    queue = []
if queue:
    for entry in queue:
        if entry.get("name") == kebab:
            return True

# Realtime daemons: System Object _realtime_pts registry (keyed snake-case).
try:
    realtime = _.get_property("_realtime_pts") or {}
except NoSuchPropertyError:
    realtime = {}
return snake in realtime or kebab in realtime
