#!moo verb queue cancel tick --on "System Object"
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Turn-based interrupt queue for Zork daemons (ZIL ENABLE/DISABLE).

Tick partitions the queue into due/pending entries; due routines fire
and recurring ones are auto-re-queued.  Per-daemon failures are caught
and the daemon is dropped from the queue rather than crashing every
command.

The queue is stored per-player as ``zstate_queue`` (list of dicts).
Recurring daemons stay queued **regardless of return value** — matching
canonical ZIL daemon semantics where ``<>``/RFALSE only means "I didn't
print anything this tick."  A daemon that wants to drop itself must
call ``_.cancel("<name>")`` explicitly; the cancel call adds the name
to a tombstone list (``zstate_drop``) that the tick loop reads to know
"skip the auto-re-queue for this one."  This avoids the pre-2026-05-17
behavior where any ``return False`` from a daemon body silently
unsubscribed the daemon — which dropped recurring patrol/combat/glow
daemons (i-fight, i-sword, i-thief, i-forest-room, i-bat) on their
first uninteresting tick.

A daemon body that re-queues itself via ``_.queue("<name>", N)`` (e.g.
the i-river / i-lantern / i-candles routines that compute a per-room
or per-state delay) wins over the auto-re-queue — the post-body queue
check sees the daemon's entry already present and leaves it alone.

:param args[0]: ``queue`` / ``cancel`` — routine-name string;
    ``tick`` takes no args.
:param args[1]: ``queue`` only — delay in turns (negative = recurring
    period).
"""

from moo.sdk import context, NoSuchPropertyError

if verb_name == "tick":
    try:
        moves = context.player.get_property("zstate_moves")
    except NoSuchPropertyError:
        moves = 0
    if moves is None:
        moves = 0
    moves += 1
    context.player.set_property("zstate_moves", moves)

    try:
        queue = context.player.get_property("zstate_queue")
    except NoSuchPropertyError:
        queue = []
    if not queue:
        return

    due = [e for e in queue if e.get("fire_at_turn", 0) <= moves]
    pending = [e for e in queue if e.get("fire_at_turn", 0) > moves]
    context.player.set_property("zstate_queue", pending)

    zthing = _.get_property("zork_thing")
    if zthing is None:
        return
    for entry in due:
        name = entry.get("name")
        if not name:
            continue
        # Verb registry stores daemons snake-cased (``i_river``); ZIL atoms
        # are kebab-case (``i-river``).
        verb = name.lower().replace("-", "_")
        crashed = False
        if zthing.has_verb(verb):
            try:
                zthing.invoke_verb(verb)
            except Exception:  # pylint: disable=broad-except
                # Drop broken daemons: re-queue would just crash next tick.
                crashed = True
        recurring = entry.get("recurring")
        if not recurring or crashed:
            continue
        # Did the daemon explicitly cancel itself?  The cancel verb pushes
        # the name onto ``zstate_drop`` so this tick loop knows not to
        # auto-re-queue (canonical ZIL "explicit DEQUEUE" semantic, not
        # "<>-return means drop me").
        drop_list = context.player.get_property("zstate_drop") or []
        if name in drop_list:
            drop_list = [n for n in drop_list if n != name]
            context.player.set_property("zstate_drop", drop_list)
            continue
        # Did the daemon re-queue itself via ``_.queue(name, new_delay)``?
        # If so, our entry is already in the post-body queue with the
        # daemon's chosen new delay — leave it alone.
        post_queue = context.player.get_property("zstate_queue") or []
        if any(e.get("name") == name for e in post_queue):
            continue
        # Default: auto-re-queue at the daemon's recurring period.
        post_queue.append(
            {
                "name": name,
                "fire_at_turn": moves + int(recurring),
                "recurring": recurring,
            }
        )
        context.player.set_property("zstate_queue", post_queue)
    return

# queue / cancel paths: both first remove the existing entry by name.
routine_name = args[0]
try:
    queue = context.player.get_property("zstate_queue")
except NoSuchPropertyError:
    queue = []
if queue is None:
    queue = []
queue = [entry for entry in queue if entry.get("name") != routine_name]

if verb_name == "queue":
    delay = args[1] if len(args) > 1 else 1
    recurring = args[2] if len(args) > 2 else None
    # ZIL convention: ENABLE <QUEUE I-FOO -N> queues a recurring daemon with
    # period N turns.  Translated routines pass the negative as ``delay``;
    # promote it to ``recurring`` so canonical at-enter daemons (i-forest-room,
    # i-fight, i-thief, i-sword) actually fire on subsequent turns.
    if delay < 0:
        recurring = -delay
        delay = -delay
    try:
        moves = context.player.get_property("zstate_moves")
    except NoSuchPropertyError:
        moves = 0
    if moves is None:
        moves = 0
    entry = {"name": routine_name, "fire_at_turn": moves + delay}
    if recurring:
        entry["recurring"] = recurring
    queue.append(entry)
    context.player.set_property("zstate_queue", queue)
    return None

# verb_name == "cancel" — push name onto the tombstone list so a
# concurrently-running tick loop knows the daemon explicitly cancelled
# (vs just returned a falsey value).  Then store the cleaned queue.
drop_list = context.player.get_property("zstate_drop") or []
if routine_name not in drop_list:
    drop_list.append(routine_name)
context.player.set_property("zstate_drop", drop_list)
context.player.set_property("zstate_queue", queue)
# Return False so legacy ``return _.cancel(name)`` idioms still terminate
# the daemon body — backwards compat for hand-rolled and ZIL-translated
# routines that use the cancel-and-return-falsey pattern.
return False
