"""
Prior-session log parsing for resume. See
``docs/source/explanation/agent-internals.md`` (Session Resume).
"""

import re
from pathlib import Path

_LOG_LINE_RE = re.compile(r"^\[(\d{2}:\d{2}:\d{2})\] \[(\w+)\] (.*)")
# Scrub Harmony/ChatML tokens from the resumed summary — keeping them
# re-poisons the new session's prompt.
_SPECIAL_TOKEN_RE = re.compile(r"<\|[A-Za-z_][A-Za-z0-9_]*\|?>")

_RESUME_KINDS = {"action", "server", "goal", "thought", "server_error"}
_RESUME_LINES = 40

_PLAN_DONE_MARKER = "[Plan] All planned rooms built."


def read_prior_session(logs_dir: Path, current_log: Path) -> tuple[str, str]:
    """
    Return ``(summary_text, last_goal)`` from the most recent prior log,
    or empty strings if none exists.
    """
    # Log names sort lexicographically == chronologically.
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

    # Plan-exhausted marker overrides the summary with a hard "call done()" line.
    if any(kind == "thought" and _PLAN_DONE_MARKER in text for kind, text in entries):
        return (
            "All planned rooms are built. Do not emit BUILD_PLAN or dig rooms. Emit DONE: now.",
            last_goal,
        )

    relevant = [(k, t) for k, t in entries if k in _RESUME_KINDS]
    recent = relevant[-_RESUME_LINES:]

    session_label = prev_log.stem
    summary_lines = [f"[Prior session: {session_label}]"]
    for kind, text in recent:
        first_line = _SPECIAL_TOKEN_RE.sub("", text.split("\n")[0])
        if len(first_line) > 120:
            first_line = first_line[:117] + "..."
        summary_lines.append(f"  [{kind}] {first_line}")
    return "\n".join(summary_lines), _SPECIAL_TOKEN_RE.sub("", last_goal)
