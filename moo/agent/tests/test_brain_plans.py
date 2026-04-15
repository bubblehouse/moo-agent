"""
Tests for moo/agent/brain_plans.py — plan persistence helpers.

All four functions are pure in the sense that their only side effects are
(a) mutating the passed ``BrainState``, (b) writing files under ``config_dir``,
and (c) calling ``on_thought`` with error/notice messages. The tests drive
them with ``tmp_path`` fixtures and a list-capturing ``on_thought`` stub.
"""

from collections.abc import Callable
from pathlib import Path

from moo.agent.brain.plans import (
    load_latest_build_plan,
    load_traversal_plan,
    save_build_plan,
    save_traversal_plan,
)
from moo.agent.brain.state import BrainState


def _capture() -> tuple[list[str], Callable[[str], None]]:
    thoughts: list[str] = []
    return thoughts, thoughts.append


# --- save_traversal_plan ---


def test_save_traversal_plan_writes_file(tmp_path):
    state = BrainState(current_plan=["The Library", "The Vault"])
    thoughts, on_thought = _capture()
    save_traversal_plan(tmp_path, state, on_thought)
    plan_path = tmp_path / "builds" / "traversal_plan.txt"
    assert plan_path.exists()
    assert plan_path.read_text() == "The Library\nThe Vault"
    assert not thoughts


def test_save_traversal_plan_no_config_dir_noops():
    state = BrainState(current_plan=["X"])
    thoughts, on_thought = _capture()
    save_traversal_plan(None, state, on_thought)
    assert not thoughts


def test_save_traversal_plan_oserror_logs_thought(tmp_path):
    state = BrainState(current_plan=["The Library"])
    # Make builds/ a file so mkdir fails
    (tmp_path / "builds").write_text("not a dir")
    thoughts, on_thought = _capture()
    save_traversal_plan(tmp_path, state, on_thought)
    assert any("Error saving" in t for t in thoughts)


# --- load_traversal_plan ---


def test_load_traversal_plan_restores_plan(tmp_path):
    (tmp_path / "builds").mkdir()
    (tmp_path / "builds" / "traversal_plan.txt").write_text("The Library\nThe Vault\n")
    state = BrainState(plan_exhausted=True)
    _, on_thought = _capture()
    load_traversal_plan(tmp_path, state, on_thought)
    assert state.current_plan == ["The Library", "The Vault"]
    assert state.plan_exhausted is False


def test_load_traversal_plan_missing_file_noops(tmp_path):
    state = BrainState()
    _, on_thought = _capture()
    load_traversal_plan(tmp_path, state, on_thought)
    assert state.current_plan == []


def test_load_traversal_plan_empty_file_noops(tmp_path):
    (tmp_path / "builds").mkdir()
    (tmp_path / "builds" / "traversal_plan.txt").write_text("\n\n")
    state = BrainState(plan_exhausted=True)
    _, on_thought = _capture()
    load_traversal_plan(tmp_path, state, on_thought)
    assert state.current_plan == []
    # Empty plan should not clear plan_exhausted
    assert state.plan_exhausted is True


def test_load_traversal_plan_no_config_dir_noops():
    state = BrainState()
    _, on_thought = _capture()
    load_traversal_plan(None, state, on_thought)
    assert state.current_plan == []


# --- load_latest_build_plan ---


def test_load_latest_build_plan_sets_plan_from_disk(tmp_path):
    builds = tmp_path / "builds"
    builds.mkdir()
    (builds / "2026-04-01-10-00.yaml").write_text(
        'phase: "First"\nrooms:\n  - name: The Library\n  - name: The Vault\n'
    )
    state = BrainState()
    _, on_thought = _capture()
    load_latest_build_plan(tmp_path, state, on_thought)
    assert state.current_plan == ["The Library", "The Vault"]
    assert state.plan_from_disk is True
    assert state.plan_exhausted is False


def test_load_latest_build_plan_picks_latest_by_name(tmp_path):
    builds = tmp_path / "builds"
    builds.mkdir()
    (builds / "2026-04-01-10-00.yaml").write_text('phase: "First"\nrooms:\n  - name: Old Room\n')
    (builds / "2026-04-02-15-00.yaml").write_text('phase: "Second"\nrooms:\n  - name: New Room\n')
    state = BrainState()
    _, on_thought = _capture()
    load_latest_build_plan(tmp_path, state, on_thought)
    assert state.current_plan == ["New Room"]


def test_load_latest_build_plan_no_builds_dir_noops(tmp_path):
    state = BrainState()
    _, on_thought = _capture()
    load_latest_build_plan(tmp_path, state, on_thought)
    assert state.current_plan == []
    assert state.plan_from_disk is False


def test_load_latest_build_plan_empty_builds_dir_noops(tmp_path):
    (tmp_path / "builds").mkdir()
    state = BrainState()
    _, on_thought = _capture()
    load_latest_build_plan(tmp_path, state, on_thought)
    assert state.current_plan == []


# --- save_build_plan ---


def test_save_build_plan_writes_yaml_and_extracts_rooms(tmp_path):
    state = BrainState()
    thoughts, on_thought = _capture()
    content = 'phase: "Build"\\nrooms:\\n  - name: The Library\\n  - name: The Vault'
    save_build_plan(tmp_path, state, on_thought, content)
    # File was written under builds/ with some timestamped name
    builds = tmp_path / "builds"
    yaml_files = list(builds.glob("*.yaml"))
    assert len(yaml_files) == 1
    assert "The Library" in yaml_files[0].read_text()
    assert state.current_plan == ["The Library", "The Vault"]
    assert state.plan_from_disk is False
    assert state.plan_exhausted is False
    assert any("Saved to" in t for t in thoughts)


def test_save_build_plan_duplicate_ignored(tmp_path):
    state = BrainState(current_plan=["The Library", "The Vault"])
    thoughts, on_thought = _capture()
    save_build_plan(
        tmp_path,
        state,
        on_thought,
        'phase: "Different"\\nrooms:\\n  - name: Other Room',
    )
    # Plan unchanged
    assert state.current_plan == ["The Library", "The Vault"]
    # No file written
    assert not (tmp_path / "builds").exists() or not list((tmp_path / "builds").glob("*.yaml"))
    assert any("Ignored duplicate" in t for t in thoughts)


def test_save_build_plan_overrides_id_only_plan(tmp_path):
    """A plan of bare room IDs (from a token page) is overridable."""
    state = BrainState(current_plan=["#89", "#90"])
    _, on_thought = _capture()
    save_build_plan(
        tmp_path,
        state,
        on_thought,
        "rooms:\\n  - name: The Library",
    )
    assert state.current_plan == ["The Library"]


def test_save_build_plan_overrides_plan_from_disk(tmp_path):
    """A plan loaded from disk is overridable by a fresh BUILD_PLAN:."""
    state = BrainState(current_plan=["Old Room"], plan_from_disk=True)
    _, on_thought = _capture()
    save_build_plan(
        tmp_path,
        state,
        on_thought,
        "rooms:\\n  - name: Fresh Room",
    )
    assert state.current_plan == ["Fresh Room"]
    assert state.plan_from_disk is False


def test_save_build_plan_sets_memory_summary(tmp_path):
    state = BrainState()
    _, on_thought = _capture()
    save_build_plan(
        tmp_path,
        state,
        on_thought,
        "rooms:\\n  - name: The Library\\n  - name: The Vault",
    )
    assert "BUILD_PLAN has been saved" in state.memory_summary
    assert "The Library | The Vault" in state.memory_summary


def test_save_build_plan_oserror_logs_thought(tmp_path):
    state = BrainState()
    (tmp_path / "builds").write_text("not a dir")
    thoughts, on_thought = _capture()
    save_build_plan(
        tmp_path,
        state,
        on_thought,
        "rooms:\\n  - name: The Library",
    )
    assert any("Error saving" in t for t in thoughts)


def test_save_build_plan_no_config_dir_noops():
    state = BrainState()
    thoughts, on_thought = _capture()
    save_build_plan(None, state, on_thought, "rooms:\\n  - name: X")
    assert state.current_plan == []
    assert not thoughts
