#!moo verb queue cancel tick --on "System Object"
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Turn-based interrupt queue for Zork daemons (ZIL ENABLE/DISABLE).

Tick partitions the queue into due/pending entries; due routines fire
and recurring ones are auto-re-queued with their original delay.  Per-
daemon failures are caught and the daemon is dropped from the queue
rather than crashing every command.

The queue is stored per-player as ``zstate_queue`` (list of dicts).

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
        cancelled = False
        if zthing.has_verb(verb):
            try:
                result = zthing.invoke_verb(verb)
                cancelled = result is False
            except Exception:  # pylint: disable=broad-except
                # Drop broken daemons: re-queue would just crash next tick.
                cancelled = True
        recurring = entry.get("recurring")
        if recurring and not cancelled:
            queue_now = context.player.get_property("zstate_queue") or []
            queue_now = [e for e in queue_now if e.get("name") != name]
            queue_now.append(
                {
                    "name": name,
                    "fire_at_turn": moves + int(recurring),
                    "recurring": recurring,
                }
            )
            context.player.set_property("zstate_queue", queue_now)
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
