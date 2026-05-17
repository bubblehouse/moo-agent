#!moo verb schedule_realtime unschedule_realtime tick_realtime --on "System Object"
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Native-task scheduling shim for ZIL daemons.

Wraps :func:`moo.sdk.invoke` and :func:`moo.sdk.cancel_scheduled_task`
so the ZIL translator can route ``<ENABLE <QUEUE I-FOO N>>`` /
``<DISABLE <INT I-FOO>>`` to native ``django-celery-beat`` scheduling
for daemons whose semantics tolerate wall-clock pacing.

ZIL distinguishes one-shot from recurring by the sign of the delay
passed to ``<QUEUE>``:

* ``<QUEUE I-MATCH 2>`` — positive delay → fire once after 2 turns,
  then exit naturally.
* ``<QUEUE I-THIEF -1>`` — negative delay → recurring period; fire
  every ``abs(N)`` turns until cancelled.

The realtime scheduler honours both modes:

* Recurring daemons (negative original delay) → ``periodic=True`` PT
  fires the ``tick_realtime`` wrapper every ``abs(N)`` seconds.  The
  wrapper invokes the named daemon verb and unschedules the PT when
  the daemon returns ``False`` (the ZIL "drop me" signal).
* One-shot daemons (positive or zero original delay) → ``periodic=False``
  ``apply_async`` with ``countdown=N``; the wrapper fires once and
  exits naturally with no PT to clean up.

The PT pk for recurring daemons is stored keyed by the snake-cased
verb name on a System Object property (``_realtime_pts``, a dict) so
the per-name lifecycle is idempotent across re-syncs and so the
at-bootstrap sweep in ``050_daemons.py`` can find stale pointers
without walking every ``PeriodicTask`` row.

:param args[0]: snake-cased verb name on ``Zork Thing`` to schedule
    (e.g. ``"i_thief"``).
:param args[1]: ``schedule_realtime`` only — delay/interval (signed).
    Negative = recurring period in seconds, non-negative = one-shot
    countdown in seconds.
"""

from moo.sdk import cancel_scheduled_task, invoke, get_scheduled_task_info

# Marker stamped into PeriodicTask.description so the 050_daemons.py
# sweep can identify rows owned by this scheduler without colliding with
# unrelated native-SDK tasks created elsewhere in the world.
ZORK_DAEMON_MARKER = "zork1-daemon"

if verb_name == "schedule_realtime":
    name = args[0]
    raw_delay = args[1] if len(args) > 1 else 1
    if not isinstance(raw_delay, int):
        try:
            raw_delay = int(raw_delay)
        except (TypeError, ValueError):
            raw_delay = 1
    # ZIL convention: negative delay means "recurring every abs(N)
    # turns"; non-negative means "fire once after N turns".
    recurring = raw_delay < 0
    delay = -raw_delay if recurring else raw_delay
    if delay <= 0:
        # One-shot with delay=0 → fire on the next celery tick.  Use a
        # 1-second countdown so apply_async doesn't reject delay=0.
        delay = 1

    zthing = this.get_property("zork_thing")
    if zthing is None or not zthing.has_verb(name):
        return None

    if not recurring:
        # One-shot dispatch via the sanctioned SDK helper — no PT, no
        # registry entry, no cancellation needed.  ``invoke`` with
        # ``periodic=False, delay=N`` calls ``apply_async`` under the
        # hood with ``countdown=N`` and returns ``None``.
        invoke(name, verb=this.get_verb("tick_realtime"), periodic=False, delay=delay)
        return None

    registry = this.get_property("_realtime_pts") or {}
    existing_pk = registry.get(name)
    if existing_pk is not None:
        info = get_scheduled_task_info(existing_pk)
        if info is not None:
            # Already scheduled at the requested cadence — no-op.
            if info.get("interval_seconds") == delay:
                return existing_pk
            # Cadence changed; drop the stale PT before scheduling fresh.
            cancel_scheduled_task(existing_pk)

    # Recurring: schedule the wrapper (``tick_realtime``) rather than
    # the daemon verb directly, so we can intercept the daemon's return
    # value and unschedule when it asks (returns False).
    pt = invoke(name, verb=this.get_verb("tick_realtime"), periodic=True, delay=delay)
    pt.description = f"{ZORK_DAEMON_MARKER}:{name}"
    pt.save()
    registry[name] = pt.pk
    this.set_property("_realtime_pts", registry)
    return pt.pk

if verb_name == "unschedule_realtime":
    name = args[0]
    registry = this.get_property("_realtime_pts") or {}
    pk = registry.pop(name, None)
    if pk is None:
        return False
    cancel_scheduled_task(pk)
    this.set_property("_realtime_pts", registry)
    return True

if verb_name == "tick_realtime":
    # Celery beat fires this verb every N seconds with the daemon's
    # snake-cased name as the single positional arg.  The daemon body
    # stays scheduled regardless of return value — matching canonical
    # ZIL daemon semantics where ``<>``/RFALSE means "I didn't print
    # anything this tick," not "drop me from the schedule."  A daemon
    # that wants to drop itself must call ``_.unschedule_realtime(name)``
    # explicitly (the i-forest-room translator output already does this
    # when the player leaves the forest).
    #
    # Auto-cleanup conditions (still trigger PT teardown):
    #   * The named verb went missing (regen rename, hand cleanup).
    #   * The daemon body raised — re-running the same crash every
    #     interval would spam celery.
    name = args[0]
    zthing = this.get_property("zork_thing")
    if zthing is None or not zthing.has_verb(name):
        registry = this.get_property("_realtime_pts") or {}
        pk = registry.pop(name, None)
        if pk is not None:
            cancel_scheduled_task(pk)
            this.set_property("_realtime_pts", registry)
        return False
    try:
        return zthing.invoke_verb(name)
    except Exception:  # pylint: disable=broad-except
        # Tear down the schedule so the crash doesn't repeat every tick.
        registry = this.get_property("_realtime_pts") or {}
        pk = registry.pop(name, None)
        if pk is not None:
            cancel_scheduled_task(pk)
            this.set_property("_realtime_pts", registry)
        raise
