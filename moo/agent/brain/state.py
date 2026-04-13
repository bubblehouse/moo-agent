"""
BrainState: mutable session state carried across LLM cycles.

All per-session fields that evolve as the agent runs are collected here in a
single dataclass. Brain holds one ``BrainState`` at ``self._state`` and reads
and mutates its fields by name.

Infrastructure fields (LLM client, compiled rules, rolling window, semaphores,
script queue, config, soul) stay on Brain — they are wiring, not session
state, and many need to survive across a hypothetical future lock wrap.

The split is intentional: extracted helpers can be written against a plain
``BrainState`` instance without needing to construct a full Brain, which makes
the many small orchestration paths (_llm_cycle, chain relay, plan save/load)
unit-testable in isolation.
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
    goal_only_count: int = 0

    # --- Token chain / stall detection ---
    foreman_paged: bool = False
    token_dispatched_at: float | None = None
    token_dispatched_to: str | None = None

    # --- Reconnect: replay prior goal after page-triggered restart ---
    prior_goal_for_reconnect: str = ""
