"""
BrainState — mutable per-session state. The split from Brain (which holds
infrastructure fields) lets helpers be tested against a plain ``BrainState``
without constructing a full Brain.
"""

from dataclasses import dataclass, field


@dataclass
class BrainState:
    """Mutable per-session state. One instance per Brain."""

    # --- Current intent ---
    current_goal: str = ""
    current_plan: list[str] = field(default_factory=list)
    plan_from_disk: bool = False
    plan_exhausted: bool = False

    # --- Done signaling ---
    session_done: bool = False
    pending_done_msg: str = ""

    # --- Rolling context ---
    memory_summary: str = ""

    # --- Build tracking ---
    rooms_built: list[str] = field(default_factory=list)

    # --- Cycle-shape counters ---
    idle_wakeup_count: int = 0
    # Two distinct cycle-budget counters, previously conflated as ``goal_only_count``:
    # - empty_cycle_count: re-cycles with zero tool calls (cap 3; nudge at 4).
    # - recycle_count: productive worker re-cycles without ``done`` (cap 10).
    # Splitting them keeps the escalation-nudge text honest and makes each
    # path's budget legible.
    empty_cycle_count: int = 0
    recycle_count: int = 0

    # --- Token chain / stall detection ---
    foreman_paged: bool = False
    token_dispatched_at: float | None = None
    token_dispatched_to: str | None = None
    last_reconnect_repage_at: float | None = None

    # --- Reconnect: replay prior goal after page-triggered restart ---
    prior_goal_for_reconnect: str = ""

    # --- Current room tracking (for redundant-teleport guard) ---
    current_room_id: str = ""  # e.g. "#67"
    current_room_name: str = ""  # e.g. "Observatory Passage"
