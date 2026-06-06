#!moo verb table_get table_put rest intbl_p copyt printt --on "System Object"
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
ZIL table primitives — pure list operations on the value passed in.

:param args[0]: ``table_get`` / ``table_put`` / ``rest`` — the list.
:param args[1]: ``table_get`` / ``table_put`` — index;
    ``rest`` — byte offset (each ZIL word = 2 bytes).
:param args[2]: ``table_put`` only — value to store.
:returns: ``table_get`` — ``list[index]`` or ``None``;
    ``table_put`` — ``None`` (mutates in place);
    ``rest`` — ``list[byte_offset // 2:]``.

``intbl_p`` (Z-machine ``INTBL?``) linear-searches a table for a value,
returning the matching sub-table (``REST``-compatible) or ``False``.
``copyt`` (``COPYT``) copies ``count`` slots src→dest (negative = backward).
``printt`` (``PRINTT``) emits ``height`` rows of ``width`` chars from a byte
grid to the current window.  All guard ``None``/non-list inputs so they are
safe before the display tables are seeded.
"""

if verb_name == "table_get":
    table = args[0] if args else None
    idx = args[1] if len(args) > 1 else 0
    if table is None or not isinstance(table, list):
        return None
    if idx is None or idx < 0 or idx >= len(table):
        return None
    return table[idx]

if verb_name == "table_put":
    table = args[0] if args else None
    idx = args[1] if len(args) > 1 else 0
    val = args[2] if len(args) > 2 else None
    if table is None or not isinstance(table, list):
        return None
    if idx is None or idx < 0:
        return None
    while len(table) <= idx:
        table.append(0)
    table[idx] = val
    return val

if verb_name == "rest":
    # ZIL <REST tbl byte_offset> shifts a table view forward by `byte_offset`
    # bytes.  Each ZIL word is 2 bytes and our representation uses one Python
    # list entry per word, so the equivalent slice is `tbl[byte_offset // 2:]`.
    # Default byte_offset is 2 (skip one word).
    table = args[0] if args else None
    offset = args[1] if len(args) > 1 else 2
    if table is None or not isinstance(table, list):
        return []
    if offset is None or offset < 0:
        return list(table)
    return table[offset // 2 :]

if verb_name == "intbl_p":
    # <INTBL? value table length [stride]> — search `table` for `value`.
    # Returns the matching sub-table (so callers can REST from it) or False.
    # `stride`/`length` byte semantics are approximated as a slot-wise scan;
    # exact pointer arithmetic awaits the real byte-addressed table model.
    value = args[0] if args else None
    table = args[1] if len(args) > 1 else None
    length = args[2] if len(args) > 2 else None
    if not isinstance(table, list):
        return False
    limit = len(table) if length is None else min(int(length), len(table))
    pos = 0
    while pos < limit:
        if table[pos] == value:
            return table[pos:]
        pos += 1
    return False

if verb_name == "copyt":
    # <COPYT src dest count> — copy `count` slots src→dest, mutating dest in
    # place.  Negative count is the ZIL overlap convention (copy backward).
    src = args[0] if args else None
    dest = args[1] if len(args) > 1 else None
    count = args[2] if len(args) > 2 else 0
    if not isinstance(src, list) or not isinstance(dest, list):
        return None
    span = abs(int(count or 0))
    order = range(span) if (count or 0) >= 0 else range(span - 1, -1, -1)
    for pos in order:
        if pos < len(src):
            while len(dest) <= pos:
                dest.append(0)
            dest[pos] = src[pos]
    return None

if verb_name == "printt":
    # <PRINTT table width [height]> — emit a byte grid to the current window.
    table = args[0] if args else None
    width = int(args[1] or 0) if len(args) > 1 else 0
    height = int(args[2] or 1) if len(args) > 2 else 1
    if not isinstance(table, list) or width <= 0:
        return None
    pos = 0
    for row in range(height):
        cells = []
        for col in range(width):
            cell = table[pos] if pos < len(table) else 32
            cells.append(chr(cell) if isinstance(cell, int) and 0 <= cell < 0x110000 else " ")
            pos += 1
        print("".join(cells))
    return None
