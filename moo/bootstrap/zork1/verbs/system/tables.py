#!moo verb table_get table_put rest --on "System Object"
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
