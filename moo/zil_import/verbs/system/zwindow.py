#!moo verb zscreen zcurset zout --on "System Object"
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""Runtime windowed-output routing for the XZIP dialect (Beyond Zork).

Beyond Zork selects the upper window (the fixed top region: stats line + font-3
auto-map) vs the lower window (the scrolling story text) with ``SCREEN``,
positions the upper-window cursor with ``CURSET``, and emits text with
``TELL``/``PRINT``/``PRINTC``.  The selection flows *across* helper calls —
``TO-TOP-WINDOW`` runs the ``SCREEN`` while a different routine does the printing
— so it can't be tracked statically; it lives at runtime in ``context.scratch``.

- ``zscreen(upper)`` — set the current output target (1 = upper/top region,
  0 = lower/scrolling).
- ``zcurset(row, col)`` — move the top-region cursor (``window_cursor``) and
  remember the position so ``printt`` can lay a multi-row grid out from it.
- ``zout(text [, newline])`` — emit to the current target: ``window_emit`` into
  the top region when upper, otherwise a normal ``print()`` into the scroll
  region (identical to the old behaviour for lower-window text).
"""

from moo.sdk import context, window_cursor, window_emit

scratch = context.scratch

if verb_name == "zscreen":
    upper = args[0] if args else 0
    if scratch is not None:
        scratch["zwin_upper"] = bool(upper)
    return None

if verb_name == "zcurset":
    row = args[0] if args else 0
    col = args[1] if len(args) > 1 else 0
    window_cursor(context.player, row, col)
    if scratch is not None:
        scratch["zwin_cursor"] = [row, col]
    return None

if verb_name == "zout":
    text = args[0] if args else ""
    newline = args[1] if len(args) > 1 else 0
    if text is None:
        text = ""
    if scratch is not None and scratch.get("zwin_upper"):
        # Upper window: paint at the top-region cursor (window_emit advances it).
        window_emit(context.player, str(text))
    else:
        print(str(text), end=("\n" if newline else ""))
    return None
