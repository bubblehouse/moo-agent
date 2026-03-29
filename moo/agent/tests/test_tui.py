"""
Tests for moo/agent/tui.py — _ScrollableOutputControl unit tests.

Tests cover the cursor-position logic that drives prompt_toolkit scrolling.
No running TUI or event loop is required.

Does not import from moo.core or trigger Django setup.
"""

from moo.agent.tui import _ScrollableOutputControl


def _make_control(*lines: str) -> _ScrollableOutputControl:
    ctrl = _ScrollableOutputControl()
    for line in lines:
        ctrl.append("ansigreen", line)
    return ctrl


def _render(ctrl: _ScrollableOutputControl, width: int = 80, height: int = 20) -> int:
    """Render the control and return the resulting cursor_y."""
    content = ctrl.create_content(width=width, height=height)
    return content.cursor_position.y


# --- autoscroll ---


def test_autoscroll_cursor_at_last_line():
    ctrl = _make_control("line1\n", "line2\n", "line3\n")
    y = _render(ctrl)
    assert y == ctrl.line_count - 1


def test_autoscroll_empty_buffer_cursor_at_zero():
    ctrl = _ScrollableOutputControl()
    y = _render(ctrl)
    assert y == 0


def test_autoscroll_grows_with_new_entries():
    ctrl = _make_control("line1\n")
    first_y = _render(ctrl)
    ctrl.append("ansigreen", "line2\n")
    second_y = _render(ctrl)
    assert second_y > first_y


# --- scroll mode ---


def test_enter_scroll_mode_pins_cursor_to_bottom():
    ctrl = _make_control("line1\n", "line2\n", "line3\n")
    _render(ctrl)  # populate line_count
    ctrl.enter_scroll_mode(ctrl.line_count - 1)
    y = _render(ctrl)
    assert y == ctrl.line_count - 1


def test_exit_scroll_mode_resumes_autoscroll():
    ctrl = _make_control("line1\n", "line2\n", "line3\n")
    _render(ctrl)
    ctrl.enter_scroll_mode(0)  # scroll to top
    ctrl.exit_scroll_mode()
    y = _render(ctrl)
    assert y == ctrl.line_count - 1


def test_scroll_up_moves_cursor_up():
    ctrl = _make_control("line1\n", "line2\n", "line3\n")
    _render(ctrl)
    ctrl.enter_scroll_mode(ctrl.line_count - 1)
    before = _render(ctrl)
    ctrl.scroll_to(ctrl.cursor_y - 1)
    after = _render(ctrl)
    assert after == before - 1


def test_scroll_down_moves_cursor_down():
    ctrl = _make_control("line1\n", "line2\n", "line3\n")
    _render(ctrl)
    ctrl.enter_scroll_mode(0)
    ctrl.scroll_to(ctrl.cursor_y + 1)
    y = _render(ctrl)
    assert y == 1


def test_scroll_up_clamps_at_zero():
    ctrl = _make_control("line1\n", "line2\n")
    _render(ctrl)
    ctrl.enter_scroll_mode(0)
    ctrl.scroll_to(ctrl.cursor_y - 100)
    assert _render(ctrl) == 0


def test_scroll_down_clamps_at_last_line():
    ctrl = _make_control("line1\n", "line2\n", "line3\n")
    _render(ctrl)
    ctrl.enter_scroll_mode(ctrl.line_count - 1)
    ctrl.scroll_to(ctrl.cursor_y + 100)
    assert _render(ctrl) == ctrl.line_count - 1


def test_line_count_updated_by_create_content():
    ctrl = _make_control("line1\n", "line2\n")
    assert ctrl.line_count == 0  # not yet rendered
    _render(ctrl)
    assert ctrl.line_count >= 2


def test_window_height_updated_by_create_content():
    ctrl = _make_control("line1\n")
    ctrl.create_content(width=80, height=30)
    assert ctrl.window_height == 30


def test_show_cursor_is_false():
    ctrl = _make_control("line1\n")
    content = ctrl.create_content(width=80, height=20)
    assert not content.show_cursor
