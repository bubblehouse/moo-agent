"""
Full-screen TUI for moo-agent.

Presents a scrolling output pane (server output, agent thoughts, actions, soul
patches) above a single-line input field. The human observer can type commands
directly; they bypass the brain and go straight to the connection.

Press Ctrl-[ (Escape) to enter scroll mode. Use arrow keys and PgUp/PgDn to
navigate the log. Press Escape again to return to live autoscroll.

Does not import from moo.core or trigger Django setup.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Callable, Literal

from prompt_toolkit import Application
from prompt_toolkit.application import get_app
from prompt_toolkit.filters import Condition
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import HSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import TextArea

_STYLES: dict[str, str] = {
    "server": "ansigreen",
    "thought": "ansiblue",
    "action": "ansired bold",
    "system": "ansigray",
    "patch": "ansiyellow",
}


@dataclass
class LogEntry:
    kind: Literal["server", "thought", "action", "system", "patch"]
    text: str
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.datetime.now().strftime("%H:%M:%S")


class MooTUI:
    """
    prompt-toolkit full-screen TUI.

    Layout:
        ┌──────────────────────────────────────┐
        │  Scrolling output pane               │
        ├──────────────────────────────────────┤
        │ > _                                  │
        └──────────────────────────────────────┘

    Ctrl-[ (Escape) enters scroll mode. Arrow keys and PgUp/PgDn navigate the
    log. Escape again resumes autoscroll.
    """

    def __init__(self, on_user_input: Callable[[str], None]):
        self._on_user_input = on_user_input
        self._output_buffer: list[tuple[str, str]] = []
        self._scroll_mode = False
        self._scroll_offset = 0  # lines from bottom; 0 = pinned to bottom

        self._output_control = FormattedTextControl(lambda: FormattedText(self._output_buffer))
        self._output_window = Window(
            content=self._output_control,
            wrap_lines=True,
            get_vertical_scroll=self._get_vertical_scroll,
        )
        self._input_field = TextArea(
            height=1,
            prompt="instruct> ",
            multiline=False,
            accept_handler=self._on_accept,
        )

        in_scroll_mode = Condition(lambda: self._scroll_mode)

        kb = KeyBindings()

        @kb.add("c-c")
        @kb.add("c-q")
        def _exit(event):
            event.app.exit()

        @kb.add("escape", eager=True)
        def _toggle_scroll_mode(event):
            if self._scroll_mode:
                self._scroll_mode = False
                self._scroll_offset = 0
            else:
                self._scroll_mode = True
                self._scroll_offset = 0
            event.app.invalidate()

        @kb.add("up", filter=in_scroll_mode)
        def _scroll_up(event):
            self._scroll_offset += 1
            event.app.invalidate()

        @kb.add("down", filter=in_scroll_mode)
        def _scroll_down(event):
            self._scroll_offset = max(0, self._scroll_offset - 1)
            event.app.invalidate()

        @kb.add("pageup", filter=in_scroll_mode)
        def _page_up(event):
            info = self._output_window.render_info
            page = info.window_height if info else 10
            self._scroll_offset += page
            event.app.invalidate()

        @kb.add("pagedown", filter=in_scroll_mode)
        def _page_down(event):
            info = self._output_window.render_info
            page = info.window_height if info else 10
            self._scroll_offset = max(0, self._scroll_offset - page)
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

    def _get_vertical_scroll(self, window) -> int:
        if not self._scroll_mode:
            return 10**9
        info = window.render_info
        if info is None:
            return 10**9
        max_scroll = max(0, info.row_count - info.window_height)
        return max(0, max_scroll - self._scroll_offset)

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

    def _on_accept(self, buf) -> bool:
        text = buf.text.strip()
        if text:
            self._on_user_input(text)
        return False  # clear the input field

    def add_entry(self, entry: LogEntry) -> None:
        """Append a log entry to the output pane and redraw."""
        style = _STYLES.get(entry.kind, "")
        line = f"[{entry.timestamp}] {entry.text}\n"
        self._output_buffer.append((style, line))
        if self._app.is_running:
            self._app.invalidate()

    async def run(self) -> None:
        """Run the TUI. Returns when the user presses Ctrl-C or Ctrl-Q."""
        await self._app.run_async()
