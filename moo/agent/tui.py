"""
Full-screen TUI for moo-agent.

Presents a scrolling output pane (server output, agent thoughts, actions, soul
patches) above a single-line input field. The human observer can type commands
directly; they bypass the brain and go straight to the connection.

Press Escape to enter scroll mode. Use arrow keys and PgUp/PgDn to
navigate the log. Press Escape again to return to live autoscroll.

Does not import from moo.core or trigger Django setup.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Literal

from prompt_toolkit import Application
from prompt_toolkit.application import get_app
from prompt_toolkit.data_structures import Point
from prompt_toolkit.filters import Condition
from prompt_toolkit.formatted_text import FormattedText, split_lines, to_formatted_text
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import HSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl, UIContent, UIControl
from prompt_toolkit.widgets import TextArea

if TYPE_CHECKING:
    from moo.agent.brain import Status

_STYLES: dict[str, str] = {
    "server": "ansiyellow",
    "server_error": "ansired bold",
    "thought": "#aaaaaa",
    "goal": "#777777",
    "action": "#ffffff",
    "system": "ansigray",
    "patch": "ansiyellow",
}

_STATUS_STYLE: dict[str, str] = {
    "ready": "ansigreen bold",
    "sleeping": "ansired bold",
    "thinking": "ansiyellow bold",
}


@dataclass
class LogEntry:
    kind: Literal["server", "server_error", "thought", "goal", "action", "system", "patch"]
    text: str
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.datetime.now().strftime("%H:%M:%S")


class _ScrollableOutputControl(UIControl):
    """
    UIControl for the output pane.

    Reports cursor_position at the last logical line when autoscrolling. In
    scroll mode the cursor tracks the viewport top, which — combined with
    directly setting Window.vertical_scroll in key handlers — produces exact
    line-by-line and page scrolling.

    window_height is captured each render so key handlers can use it for page
    calculations without calling any render_info API.
    """

    def __init__(self) -> None:
        self._fragments: list[tuple[str, str]] = []
        self._cursor_y: int = 0
        self._autoscroll: bool = True
        self._line_count: int = 0
        self._window_height: int = 20  # updated by create_content

    @property
    def line_count(self) -> int:
        return self._line_count

    @property
    def window_height(self) -> int:
        return self._window_height

    @property
    def cursor_y(self) -> int:
        return self._cursor_y

    @property
    def autoscroll(self) -> bool:
        return self._autoscroll

    def enter_scroll_mode(self, viewport_top: int) -> None:
        self._autoscroll = False
        self._cursor_y = max(0, min(viewport_top, max(0, self._line_count - 1)))

    def exit_scroll_mode(self) -> None:
        self._autoscroll = True

    def scroll_to(self, line: int) -> None:
        self._cursor_y = max(0, min(line, max(0, self._line_count - 1)))

    def is_focusable(self) -> bool:
        return False

    def append(self, style: str, text: str) -> None:
        self._fragments.append((style, text))

    def create_content(self, width: int, height: int | None) -> UIContent:
        if height is not None:
            self._window_height = height

        lines = list(split_lines(to_formatted_text(self._fragments)))
        if not lines:
            lines = [[]]
        self._line_count = len(lines)

        if self._autoscroll:
            y = self._line_count - 1
        else:
            y = max(0, min(self._cursor_y, self._line_count - 1))

        def get_line(i: int) -> list:
            return lines[i] if i < self._line_count else []

        return UIContent(
            get_line=get_line,
            line_count=self._line_count,
            cursor_position=Point(x=0, y=y),
            show_cursor=False,
        )


class MooTUI:
    """
    prompt-toolkit full-screen TUI.

    Layout:
        ┌──────────────────────────────────────┐
        │  Scrolling output pane               │
        ├──────────────────────────────────────┤
        │ interact> _                          │
        └──────────────────────────────────────┘

    Escape enters scroll mode. Arrow keys and PgUp/PgDn navigate the log.
    Escape again resumes autoscroll.
    """

    def __init__(self, on_user_input: Callable[[str], None]):
        self._on_user_input = on_user_input
        self._scroll_mode = False
        self._status_name = "interact"

        self._output_control = _ScrollableOutputControl()
        self._output_window = Window(
            content=self._output_control,
            wrap_lines=True,
        )
        self._input_field = TextArea(
            height=1,
            prompt=self._get_prompt,
            multiline=False,
            accept_handler=self._on_accept,
        )

        in_scroll_mode = Condition(lambda: self._scroll_mode)

        kb = KeyBindings()

        @kb.add("c-c", eager=True)
        @kb.add("c-d", eager=True)
        @kb.add("c-q", eager=True)
        def _exit(event):
            event.app.exit()

        @kb.add("escape", eager=True)
        def _toggle_scroll_mode(event):
            ctrl = self._output_control
            if self._scroll_mode:
                self._scroll_mode = False
                ctrl.exit_scroll_mode()
            else:
                self._scroll_mode = True
                ctrl.enter_scroll_mode(self._output_window.vertical_scroll)
            event.app.invalidate()

        @kb.add("up", filter=in_scroll_mode, eager=True)
        def _scroll_up(event):
            ctrl = self._output_control
            ctrl.scroll_to(ctrl.cursor_y - 1)
            self._output_window.vertical_scroll = ctrl.cursor_y
            event.app.invalidate()

        @kb.add("down", filter=in_scroll_mode, eager=True)
        def _scroll_down(event):
            ctrl = self._output_control
            ctrl.scroll_to(ctrl.cursor_y + 1)
            self._output_window.vertical_scroll = ctrl.cursor_y
            event.app.invalidate()

        @kb.add("pageup", filter=in_scroll_mode, eager=True)
        def _page_up(event):
            ctrl = self._output_control
            ctrl.scroll_to(ctrl.cursor_y - max(1, ctrl.window_height - 1))
            self._output_window.vertical_scroll = ctrl.cursor_y
            event.app.invalidate()

        @kb.add("pagedown", filter=in_scroll_mode, eager=True)
        def _page_down(event):
            ctrl = self._output_control
            ctrl.scroll_to(ctrl.cursor_y + max(1, ctrl.window_height - 1))
            self._output_window.vertical_scroll = ctrl.cursor_y
            event.app.invalidate()

        layout = Layout(
            HSplit(
                [
                    self._output_window,
                    Window(
                        height=1,
                        content=FormattedTextControl(self._get_separator_text),
                    ),
                    self._input_field,
                ]
            )
        )

        self._app = Application(
            layout=layout,
            key_bindings=kb,
            full_screen=True,
        )

    def _get_separator_text(self) -> FormattedText:
        try:
            width = get_app().output.get_size().columns
        except Exception:  # pylint: disable=broad-exception-caught
            width = 80
        if self._scroll_mode:
            msg = " SCROLL  \u2191\u2193 PgUp/PgDn  ESC to resume "
            padding = max(0, width - len(msg))
            left = "\u2500" * (padding // 2)
            right = "\u2500" * (padding - padding // 2)
            return FormattedText([("ansiyellow bold", left + msg + right)])
        return FormattedText([("", "\u2500" * width)])

    def _get_prompt(self) -> FormattedText:
        style = _STATUS_STYLE.get(self._status_name, "")
        return FormattedText([(style, f"{self._status_name}> ")])

    def _on_accept(self, buf) -> bool:
        text = buf.text.strip()
        if text:
            self._on_user_input(text)
        return False  # clear the input field

    def set_status(self, status: "Status") -> None:
        """Update the status indicator in the prompt. Safe to call from any coroutine."""
        self._status_name = status.value
        if self._app.is_running:
            self._app.invalidate()

    def add_entry(self, entry: LogEntry) -> None:
        """Append a log entry to the output pane and redraw."""
        style = _STYLES.get(entry.kind, "")
        line = f"[{entry.timestamp}] {entry.text}\n"
        self._output_control.append(style, line)
        if self._app.is_running:
            self._app.invalidate()

    async def run(self) -> None:
        """Run the TUI. Returns when the user presses Ctrl-C, Ctrl-D, or Ctrl-Q."""
        await self._app.run_async()
