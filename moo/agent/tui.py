"""
Full-screen TUI for moo-agent.

Presents a scrolling output pane (server output, agent thoughts, actions, soul
patches) above a single-line input field. The human observer can type commands
directly; they bypass the brain and go straight to the connection.

Does not import from moo.core or trigger Django setup.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Callable, Literal

from prompt_toolkit import Application
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
    """

    def __init__(self, on_user_input: Callable[[str], None]):
        self._on_user_input = on_user_input
        self._output_buffer: list[tuple[str, str]] = []

        self._output_control = FormattedTextControl(lambda: FormattedText(self._output_buffer))
        self._output_window = Window(
            content=self._output_control,
            wrap_lines=True,
            get_vertical_scroll=lambda w: 10**9,
        )
        self._input_field = TextArea(
            height=1,
            prompt="instruct> ",
            multiline=False,
            accept_handler=self._on_accept,
        )

        kb = KeyBindings()

        @kb.add("c-c")
        @kb.add("c-q")
        def _exit(event):
            event.app.exit()

        layout = Layout(
            HSplit(
                [
                    self._output_window,
                    Window(height=1, char="─"),
                    self._input_field,
                ]
            )
        )

        self._app = Application(
            layout=layout,
            key_bindings=kb,
            full_screen=True,
        )

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
