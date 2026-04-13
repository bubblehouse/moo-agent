"""
Prior-session log parsing for moo-agent resume.

Reads the most recent log file in a logs directory and extracts a short
summary plus the last recorded goal, so a fresh run can pick up where the
previous one left off without replaying the full history.

Does not import from moo.core or moo.agent.brain — pure filesystem + regex.
"""

import re
from pathlib import Path

_LOG_LINE_RE = re.compile(r"^\[(\d{2}:\d{2}:\d{2})\] \[(\w+)\] (.*)")
# Strip Harmony/ChatML special tokens that may have leaked into a prior
# log as [thought] text. Keeping them in the resumed summary re-poisons the
# new session's prompt (see brain.py _SPECIAL_TOKEN_RE).
_SPECIAL_TOKEN_RE = re.compile(r"<\|[A-Za-z_][A-Za-z0-9_]*\|?>")

# Kinds that are meaningful for session resumption; skip system/patch noise.
_RESUME_KINDS = {"action", "server", "goal", "thought", "server_error"}
# How many recent entries to include in the prior-session summary.
_RESUME_LINES = 40

_PLAN_DONE_MARKER = "[Plan] All planned rooms built."


def read_prior_session(logs_dir: Path, current_log: Path) -> tuple[str, str]:
    """
    Find the most recent previous log file and extract session context.

    Returns (summary_text, last_goal). Both are empty strings if no prior log
    exists. The summary is injected into the brain's memory window so the
    agent knows where it left off without replaying the full history.
    """
    # Logs are named YYYY-MM-DDTHH-MM-SS.log, so lexicographic order equals
    # chronological order.
    prior_logs = sorted(p for p in logs_dir.glob("*.log") if p != current_log)
    if not prior_logs:
        return "", ""

    prev_log = prior_logs[-1]
    raw_lines = prev_log.read_text(encoding="utf-8").splitlines()

    entries: list[tuple[str, str]] = []
    cur_kind: str = ""
    cur_text: str = ""
    in_entry: bool = False
    for line in raw_lines:
        m = _LOG_LINE_RE.match(line)
        if m:
            if in_entry:
                entries.append((cur_kind, cur_text))
            _, cur_kind, cur_text = m.groups()
            in_entry = True
        elif in_entry:
            cur_text = cur_text + "\n" + line
    if in_entry:
        entries.append((cur_kind, cur_text))

    last_goal = ""
    for kind, text in reversed(entries):
        if kind == "goal":
            last_goal = text.removeprefix("[Goal] ").strip()
            break

    # If the prior session ended with a plan-exhaustion signal, override the
    # summary so the new session starts knowing all rooms are built.
    if any(kind == "thought" and _PLAN_DONE_MARKER in text for kind, text in entries):
        return (
            "All planned rooms are built. Do not emit BUILD_PLAN or dig rooms. Emit DONE: now.",
            last_goal,
        )

    relevant = [(k, t) for k, t in entries if k in _RESUME_KINDS]
    recent = relevant[-_RESUME_LINES:]

    session_label = prev_log.stem  # e.g. "2026-03-28T23-33-51"
    summary_lines = [f"[Prior session: {session_label}]"]
    for kind, text in recent:
        first_line = _SPECIAL_TOKEN_RE.sub("", text.split("\n")[0])
        if len(first_line) > 120:
            first_line = first_line[:117] + "..."
        summary_lines.append(f"  [{kind}] {first_line}")
    return "\n".join(summary_lines), _SPECIAL_TOKEN_RE.sub("", last_goal)
