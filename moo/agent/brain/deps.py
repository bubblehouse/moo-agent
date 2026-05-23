"""
``BrainDeps`` — the ``RunContext.deps`` payload Stage-2 tools see.

Brain builds one per ``agent.run()`` cycle from current ``BrainState``.
Tools dispatch MOO commands via ``deps.connection.request()``; side-effecting
tools mutate the flagged fields, and Brain folds them back onto ``self._state``
after the run returns.
"""

from dataclasses import dataclass
from typing import Callable

from asynciolimiter import LeakyBucketLimiter

from moo.agent.connection import MooConnection


@dataclass(slots=True)
class BrainDeps:
    connection: MooConnection
    limiter: LeakyBucketLimiter
    soul_name: str

    current_room_id: str
    current_room_name: str

    on_thought: Callable[[str], None]
    on_window_append: Callable[[str], None]

    session_done: bool = False
    pending_done_msg: str = ""
    foreman_paged: bool = False
    token_dispatched_at: float | None = None
    token_dispatched_to: str = ""
    # Incremented by ``respond()``; used to escalate the nudge text so a
    # confused model stuck in a respond-loop sees an explicit "emit
    # final_result now" prompt before the hard ``tool_calls_per_cycle`` cap
    # fires. Reset implicitly each cycle because ``_make_deps`` builds a
    # fresh ``BrainDeps`` per ``agent.run()``.
    respond_count: int = 0
