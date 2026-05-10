"""Optional pylint validation of generated bootstrap output.

Per-file linting hooked into the generator's write path: each generated
``.py`` file is scored immediately after it lands on disk.  Anything
below the configured threshold raises ``RuntimeError`` from inside the
import — the operator sees the offending file and pylint's per-message
output before any downstream regen work happens.

Usage from the CLI: ``uv run python -m extras.zil_import <files> --lint``
enables the per-file check (off by default — pylint's first-file warmup
is ~0.8s on this machine and warm calls are ~0.04-0.1s, so the full
~800-file regen takes 30-60s extra with ``--lint`` on).

Uses the pylint library API (``pylint.lint.PyLinter``) in-process
rather than shelling out — keeps a single linter alive across the regen
so plugin discovery happens once.

Configuration is read from ``pylintrc`` at the repo root; the threshold
is the ``global_note`` evaluation that pylintrc's ``[REPORTS]`` section
computes (default 10 - 5*(E + W + R + C) / statements).
"""

from __future__ import annotations

import logging
from io import StringIO
from pathlib import Path

log = logging.getLogger(__name__)


class Linter:
    """Long-lived pylint runner that scores files one at a time.

    Lazy-imports pylint and pylint-django so a regen that doesn't pass
    ``--lint`` doesn't pay the ~1s pylint import cost.
    """

    def __init__(self, *, config_file: str = "pylintrc", threshold: float = 9.0) -> None:
        # Lazy imports — pylint pulls in astroid + pylint_django + a
        # bunch of checker plugins that add ~1s to process startup.
        from pylint.config.config_initialization import (  # pylint: disable=import-outside-toplevel
            _config_initialization,
        )
        from pylint.lint import PyLinter  # pylint: disable=import-outside-toplevel
        from pylint.reporters.text import TextReporter  # pylint: disable=import-outside-toplevel

        self._linter = PyLinter()
        self._linter.load_default_plugins()
        # ``_config_initialization`` reads ``pylintrc`` and applies the
        # config + plugin loads.  Must be called before ``check()``.
        _config_initialization(
            self._linter,
            [],
            reporter=TextReporter(output=StringIO()),
            config_file=config_file,
        )
        self.threshold = threshold
        self._TextReporter = TextReporter  # cached for set_reporter calls

    def check_file(self, path: Path) -> tuple[float | None, str]:
        """Run pylint on ``path``, return ``(score, output_text)``.

        ``score`` is None when pylint analysed zero statements (e.g. an
        empty file or a comment-only stub) — ``check_or_raise`` skips
        the threshold check in that case.
        """
        out = StringIO()
        self._linter.set_reporter(self._TextReporter(output=out))
        # ``open()`` resets per-run stats so each file gets an isolated
        # score.  Without it, statement / message counts accumulate
        # across calls and ``global_note`` reflects the cumulative state.
        self._linter.open()
        self._linter.check([str(path)])
        # ``generate_reports()`` is what computes ``global_note``.
        # ``check()`` alone leaves the score unset (= 0).
        self._linter.generate_reports()
        return self._linter.stats.global_note, out.getvalue()

    def check_or_raise(self, path: Path) -> None:
        """Raise ``RuntimeError`` when ``path`` scores below ``self.threshold``.

        No-op when pylint produced no score (empty file, all comments).
        """
        score, output = self.check_file(path)
        if score is None:
            return
        if score < self.threshold:
            raise RuntimeError(
                f"pylint score {score:.2f}/10 for {path} is below threshold "
                f"{self.threshold:.2f}.\n\n--- pylint findings ---\n{output}"
            )
        log.debug("pylint OK (%.2f/10): %s", score, path)
