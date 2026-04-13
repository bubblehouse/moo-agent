# -*- coding: utf-8 -*-

from pathlib import Path

from moo.agent.session_log import read_prior_session as _read_prior_session

_SAMPLE_LOG = """\
[23:33:52] [system] Connected. Soul loaded: Builder
[23:33:52] [action] look
[23:33:55] [goal] [Goal] Survey existing world state before expanding the mansion
[23:33:55] [thought] Let me survey what already exists before building anything new.
[23:33:55] [action] @realm $room
[23:33:55] [server] Generic Room (#5)
  Mail Distribution Center (#6)
  The Laboratory (#19)
[23:34:36] [goal] [Goal] Visit The Boiler Room
[23:34:36] [action] go north
[23:34:36] [server] You arrive at #35 (The Boiler Room).
[23:45:27] [action] @edit property text on #45 with "The needle is buried in the red zone."
[23:45:27] [server] Set property text on #45 (pressure gauge)
"""


def _write_log(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


def test_no_prior_log_returns_empty(tmp_path):
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    current = logs_dir / "2026-03-29T10-00-00.log"
    summary, goal = _read_prior_session(logs_dir, current)
    assert summary == ""
    assert goal == ""


def test_extracts_last_goal(tmp_path):
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    _write_log(logs_dir, "2026-03-28T23-33-51.log", _SAMPLE_LOG)
    current = logs_dir / "2026-03-29T10-00-00.log"
    _, goal = _read_prior_session(logs_dir, current)
    assert goal == "Visit The Boiler Room"


def test_summary_contains_recent_actions(tmp_path):
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    _write_log(logs_dir, "2026-03-28T23-33-51.log", _SAMPLE_LOG)
    current = logs_dir / "2026-03-29T10-00-00.log"
    summary, _ = _read_prior_session(logs_dir, current)
    assert "[action] go north" in summary
    assert "[server] You arrive at #35 (The Boiler Room)." in summary
    assert "[Prior session: 2026-03-28T23-33-51]" in summary


def test_summary_excludes_system_entries(tmp_path):
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    _write_log(logs_dir, "2026-03-28T23-33-51.log", _SAMPLE_LOG)
    current = logs_dir / "2026-03-29T10-00-00.log"
    summary, _ = _read_prior_session(logs_dir, current)
    assert "[system]" not in summary


def test_most_recent_prior_log_selected(tmp_path):
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    older = "[10:00:00] [goal] [Goal] Old goal\n"
    newer = "[11:00:00] [goal] [Goal] New goal\n"
    _write_log(logs_dir, "2026-03-27T10-00-00.log", older)
    _write_log(logs_dir, "2026-03-28T11-00-00.log", newer)
    current = logs_dir / "2026-03-29T10-00-00.log"
    _, goal = _read_prior_session(logs_dir, current)
    assert goal == "New goal"


def test_current_log_excluded_from_candidates(tmp_path):
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    current = _write_log(logs_dir, "2026-03-29T10-00-00.log", "[10:00:00] [goal] [Goal] Current goal\n")
    _, goal = _read_prior_session(logs_dir, current)
    assert goal == ""


def test_multiline_server_output_merged(tmp_path):
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    log_content = (
        "[10:00:00] [action] @realm $room\n"
        "[10:00:01] [server] Generic Room (#5)\n"
        "  Mail Distribution Center (#6)\n"
        "  The Laboratory (#19)\n"
        "[10:00:02] [goal] [Goal] Done\n"
    )
    _write_log(logs_dir, "2026-03-28T10-00-00.log", log_content)
    current = logs_dir / "2026-03-29T10-00-00.log"
    summary, _ = _read_prior_session(logs_dir, current)
    assert "[server] Generic Room (#5)" in summary
