"""
ZIL daemon tick-mode classifier.

Decides whether a translated ``<QUEUE I-FOO N>`` / ``<ENABLE <INT I-FOO>>``
should be routed through the native real-time scheduler
(:func:`moo.sdk.invoke` via ``_.schedule_realtime``) or through the
turn-based per-player queue (``_.queue`` / ``_.cancel`` backed by
:mod:`moo.bootstrap.zork1.verbs.system.queue`).

The native scheduler fires the daemon's verb every ``delay`` *seconds* via
``django-celery-beat``; the turn queue fires every ``delay`` *player
commands*.  Daemons that count player turns (fuel decay, rage meter,
healing per round, per-round combat) must stay on the turn queue;
daemons that respond to spatial / event state (patrol, ambient
RNG, tide flips) tolerate real-time pacing.

The default for unclassified routines is ``"turn"`` so a future port
that adds a daemon without updating this table preserves the existing
(safe) semantics.
"""

from __future__ import annotations

# Routines that explicitly run on the native real-time scheduler.
# Names are kebab-case ZIL atoms (matching how the translator emits them).
_REALTIME: frozenset[str] = frozenset(
    {
        # NPC patrol — event-driven, scope-checked on each fire.
        "i-thief",
        # Ambient room chatter — fires while player is in a forest
        # room; the daemon body returns False when scope ends and
        # the realtime scheduler's tick wrapper auto-unschedules.
        "i-forest-room",
        # One-shot transitions.
        "i-match",
        "i-xb",
        "i-xbh",
        "i-xc",
        # Slowly-flooding side puzzle; phasing is acceptable.
        "i-maint-room",
        # NOTE: ``i-river`` / ``i-rfill`` / ``i-rempty`` / ``i-sword``
        # stay on the turn queue.  Their state changes are timing-
        # critical (the canonical Zork playthrough expects each
        # boat-drift / tide-flip / glow-update to land on a specific
        # player turn) and the smoke harness exercises that cadence
        # directly.  Real-time scheduling shifts the scoring window
        # in ways the harness can't tolerate.
    }
)


def classify(routine: str) -> str:
    """
    Return the tick mode for a ZIL routine name.

    :param routine: Kebab-case ZIL routine atom (e.g. ``"i-lantern"``).
    :returns: ``"realtime"`` if the routine is on the native scheduler
        allowlist, ``"turn"`` otherwise.
    """
    return "realtime" if routine.lower() in _REALTIME else "turn"


def realtime_routines() -> frozenset[str]:
    """
    Expose the allowlist (read-only) for the at-startup enable loop.

    :returns: The frozen set of kebab-case routine names that run on
        the native scheduler.
    """
    return _REALTIME
