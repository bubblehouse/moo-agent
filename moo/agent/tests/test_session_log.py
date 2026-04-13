"""
Tests for moo/agent/session_log.py.

Previously untested. Exercises the log-parsing fallbacks in
read_prior_session including empty directories, goal extraction, special-token
scrubbing, long-line truncation, the plan-done marker shortcut, and
multi-line entry continuation.
"""

from pathlib import Path

from moo.agent.session_log import read_prior_session


def _write_log(logs_dir: Path, ts: str, lines: list[str]) -> Path:
    p = logs_dir / f"{ts}.log"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def test_empty_logs_dir_returns_empty(tmp_path):
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    current = logs_dir / "2026-04-13T10-00-00.log"
    summary, goal = read_prior_session(logs_dir, current)
    assert summary == ""
    assert goal == ""


def test_only_current_log_returns_empty(tmp_path):
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    current = _write_log(logs_dir, "2026-04-13T10-00-00", ["[10:00:00] [system] Starting"])
    summary, goal = read_prior_session(logs_dir, current)
    assert summary == ""
    assert goal == ""


def test_most_recent_prior_log_chosen(tmp_path):
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    _write_log(logs_dir, "2026-04-13T09-00-00", ["[09:00:00] [goal] [Goal] older goal"])
    _write_log(logs_dir, "2026-04-13T09-30-00", ["[09:30:00] [goal] [Goal] newer goal"])
    current = logs_dir / "2026-04-13T10-00-00.log"
    current.write_text("", encoding="utf-8")
    summary, goal = read_prior_session(logs_dir, current)
    assert goal == "newer goal"
    assert "2026-04-13T09-30-00" in summary


def test_last_goal_extracted(tmp_path):
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    _write_log(
        logs_dir,
        "2026-04-13T09-00-00",
        [
            "[09:00:00] [goal] [Goal] first goal",
            "[09:05:00] [action] look",
            "[09:10:00] [goal] [Goal] last goal",
            "[09:15:00] [action] go north",
        ],
    )
    current = logs_dir / "2026-04-13T10-00-00.log"
    _, goal = read_prior_session(logs_dir, current)
    assert goal == "last goal"


def test_goal_prefix_stripped(tmp_path):
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    _write_log(logs_dir, "2026-04-13T09-00-00", ["[09:00:00] [goal] [Goal] build the library"])
    current = logs_dir / "2026-04-13T10-00-00.log"
    _, goal = read_prior_session(logs_dir, current)
    assert goal == "build the library"


def test_no_goal_returns_empty_goal(tmp_path):
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    _write_log(
        logs_dir,
        "2026-04-13T09-00-00",
        ["[09:00:00] [action] look", "[09:01:00] [server] You see a room."],
    )
    current = logs_dir / "2026-04-13T10-00-00.log"
    summary, goal = read_prior_session(logs_dir, current)
    assert goal == ""
    # But a summary should still be produced from the actions/server lines
    assert "look" in summary


def test_plan_done_marker_overrides_summary(tmp_path):
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    _write_log(
        logs_dir,
        "2026-04-13T09-00-00",
        [
            "[09:00:00] [goal] [Goal] build five rooms",
            "[09:30:00] [thought] [Plan] All planned rooms built.",
        ],
    )
    current = logs_dir / "2026-04-13T10-00-00.log"
    summary, goal = read_prior_session(logs_dir, current)
    assert "All planned rooms are built" in summary
    assert "Emit DONE" in summary
    assert goal == "build five rooms"


def test_long_line_truncated_to_120_chars(tmp_path):
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    long_text = "x" * 200
    _write_log(logs_dir, "2026-04-13T09-00-00", [f"[09:00:00] [server] {long_text}"])
    current = logs_dir / "2026-04-13T10-00-00.log"
    summary, _ = read_prior_session(logs_dir, current)
    # Each summary line has a "  [kind] " prefix plus the truncated text
    # ending in "..." (117 chars + "...").
    assert "..." in summary
    for line in summary.split("\n")[1:]:
        # Strip leading "  [server] " prefix before length check
        payload = line.split("] ", 1)[-1]
        assert len(payload) <= 120


def test_short_line_not_truncated(tmp_path):
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    _write_log(logs_dir, "2026-04-13T09-00-00", ["[09:00:00] [server] brief"])
    current = logs_dir / "2026-04-13T10-00-00.log"
    summary, _ = read_prior_session(logs_dir, current)
    assert "brief" in summary
    assert "..." not in summary


def test_special_tokens_stripped_from_summary(tmp_path):
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    _write_log(
        logs_dir,
        "2026-04-13T09-00-00",
        ["[09:00:00] [thought] <|startoftext|>plan<|endoftext|>"],
    )
    current = logs_dir / "2026-04-13T10-00-00.log"
    summary, _ = read_prior_session(logs_dir, current)
    assert "<|" not in summary
    assert "plan" in summary


def test_special_tokens_stripped_from_goal(tmp_path):
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    _write_log(
        logs_dir,
        "2026-04-13T09-00-00",
        ["[09:00:00] [goal] [Goal] <|assistant|>build the manor<|end|>"],
    )
    current = logs_dir / "2026-04-13T10-00-00.log"
    _, goal = read_prior_session(logs_dir, current)
    assert "<|" not in goal
    assert "build the manor" in goal


def test_resume_kinds_filtered(tmp_path):
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    _write_log(
        logs_dir,
        "2026-04-13T09-00-00",
        [
            "[09:00:00] [system] Connecting to localhost...",
            "[09:00:05] [action] look",
            "[09:00:10] [operator] [Operator]: ignored",
        ],
    )
    current = logs_dir / "2026-04-13T10-00-00.log"
    summary, _ = read_prior_session(logs_dir, current)
    assert "Connecting" not in summary
    assert "ignored" not in summary
    assert "look" in summary


def test_multi_line_entry_continuation(tmp_path):
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    _write_log(
        logs_dir,
        "2026-04-13T09-00-00",
        [
            "[09:00:00] [server] first line",
            "continuation of the first entry",
            "[09:00:05] [action] go north",
        ],
    )
    current = logs_dir / "2026-04-13T10-00-00.log"
    summary, _ = read_prior_session(logs_dir, current)
    # Only the first line of a multi-line entry appears in the summary
    assert "first line" in summary
    assert "go north" in summary
    # The continuation text is collapsed: only the first \n-split segment shows
    assert "continuation of the first entry" not in summary


def test_recent_40_entries_cap(tmp_path):
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    lines = [f"[09:00:{i:02d}] [action] cmd{i}" for i in range(60)]
    _write_log(logs_dir, "2026-04-13T09-00-00", lines)
    current = logs_dir / "2026-04-13T10-00-00.log"
    summary, _ = read_prior_session(logs_dir, current)
    # First row is the [Prior session] header; body is at most 40 rows
    body = [line for line in summary.split("\n") if line.startswith("  [")]
    assert len(body) <= 40
    # The tail (cmd59) should be present; the head (cmd0) should not
    assert "cmd59" in summary
    assert "cmd0 " not in summary


def test_session_label_in_summary_header(tmp_path):
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    _write_log(logs_dir, "2026-04-13T09-30-15", ["[09:30:15] [action] look"])
    current = logs_dir / "2026-04-13T10-00-00.log"
    summary, _ = read_prior_session(logs_dir, current)
    assert summary.startswith("[Prior session: 2026-04-13T09-30-15]")
