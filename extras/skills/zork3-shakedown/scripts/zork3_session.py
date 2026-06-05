#!/usr/bin/env python3
"""Thin per-game wrapper around the shared shakedown harness.

All logic lives in extras/skills/_shared/moo_session.py; this file only
binds the zork3 dataset slug so the command examples in SKILL.md read as
zork3_session.py start --reset etc.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_shared"))

from moo_session import run  # noqa: E402  # pylint: disable=wrong-import-position

if __name__ == "__main__":
    sys.exit(run("zork3"))
