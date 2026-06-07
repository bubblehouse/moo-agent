#!moo verb zscreen zcurset zout zdirout --on "System Object"
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""Runtime windowed-output routing for the XZIP dialect (Beyond Zork).

Beyond Zork selects the upper window (the fixed top region: stats line + font-3
auto-map) vs the lower window (the scrolling story text) with ``SCREEN``,
positions the upper-window cursor with ``CURSET``, emits text with
``TELL``/``PRINT``/``PRINTC``, and captures text into a table buffer with
``DIROUT``.  The selection flows *across* helper calls — ``TO-TOP-WINDOW`` runs
the ``SCREEN`` while a different routine does the printing — so it can't be
tracked statically; it lives at runtime in ``context.scratch``.

- ``zscreen(upper)`` — set the current output target (1 = upper/top region,
  0 = lower/scrolling).
- ``zcurset(row, col)`` — move the top-region cursor (``window_cursor``) and
  remember the position so ``printt`` can lay a multi-row grid out from it.
- ``zdirout(mode [, table])`` — Z-machine output-stream control.  ``D-TABLE-ON``
  (3) redirects subsequent output into ``table`` (Z-machine stream 3: a length
  word at offset 0, characters from byte 2); ``D-TABLE-OFF`` (-3) ends it.
  Beyond Zork builds the centered status line this way: ``setup_sline`` opens a
  capture into AUX-TABLE, ``say_here`` prints the room name *into* it, then
  ``center_sline`` copies it into SLINE for ``printt`` to paint.  Screen on/off
  (1 / -1) is ignored.
- ``zout(text [, newline])`` — emit to the current target: into the DIROUT table
  buffer when capture is active, else ``window_emit`` into the top region when
  the upper window is selected, else a normal ``print()`` into the scroll region
  (identical to the old behaviour for lower-window text).
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

if verb_name == "zdirout":
    mode = args[0] if args else 0
    table = args[1] if len(args) > 1 else None
    if scratch is not None:
        if mode == 3 and isinstance(table, list):
            # D-TABLE-ON: start capturing into `table`; reset its length word.
            while len(table) < 2:
                table.append(0)
            table[0] = 0
            table[1] = 0
            scratch["zdirout"] = table
        elif mode == -3:
            # D-TABLE-OFF: stop capturing.
            scratch["zdirout"] = None
        # mode 1 / -1 (screen on/off) is ignored.
    return None

if verb_name == "zout":
    text = args[0] if args else ""
    newline = args[1] if len(args) > 1 else 0
    if text is None:
        text = ""
    text = str(text)
    buffer = scratch.get("zdirout") if scratch is not None else None
    if isinstance(buffer, list):
        # DIROUT capture: append characters after the length word (offset 0),
        # data starting at byte 2, and keep the count in word 0.
        count = buffer[0] if buffer and isinstance(buffer[0], int) else 0
        for ch in text:
            pos = 2 + count
            while len(buffer) <= pos:
                buffer.append(0)
            buffer[pos] = ord(ch)
            count += 1
        buffer[0] = count
    elif scratch is not None and scratch.get("zwin_upper"):
        # Upper window: paint at the top-region cursor (window_emit advances it).
        window_emit(context.player, text)
    else:
        print(text, end=("\n" if newline else ""))
    return None
