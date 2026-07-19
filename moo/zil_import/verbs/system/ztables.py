#!moo verb zaddr_rest zaddr_get zaddr_put zaddr_copyt zaddr_intbl_p --on "System Object"
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""Byte-addressed table/pointer model for the XZIP dialect (Beyond Zork).

The EZIP table primitives (``rest``/``table_get``/``copyt`` in ``tables.py``)
treat a table as a Python list and ``REST`` as a list slice.  Beyond Zork's
DBOX/SLINE buffer-scroll routines (``JUSTIFY-DBOX``, ``CENTER-SLINE``,
``SETUP-DBOX``, ``DISPLAY-DBOX``) instead do real Z-machine **pointer
arithmetic** — ``<+ .BASE off>``, ``<- .PTR .BASE>``, pointer comparisons, and
``PUTB``/``COPYT`` through a ``REST`` view that must mutate the *original*
backing table.  Slices can't express that.

Model: a **pointer is a plain integer address** (so the translated ``base +
off`` / comparisons work natively, no custom class fighting the sandbox).  A
per-task registry in ``context.scratch`` lays each table out at a
non-overlapping base address; resolving an address scans for the owning table
and returns ``(backing_list, offset)``.  Addresses count **cells** — for the
``(BYTE)`` ITABLE buffers these routines use, one cell is one byte, so a byte
offset is a cell offset (no word ``//2``).  Mutation is in place; the
``get_property`` session cache returns the same list within a turn, so writes
are visible to later reads in the same ``look`` (the buffers are rebuilt each
turn, so no cross-turn persistence is needed).

Addresses start at 1 — address 0 stays ZIL FALSE / null, so ``INTBL?`` can
return 0 for "not found" and a real table cell never collides with it.

Polymorphic: every op accepts either a list (a table value straight from
``zstate_get`` / ``getp``) or an int address, normalising via ``addr_of``.
"""

from moo.sdk import context


def reg_lookup():
    """Return the per-task table-address registry, creating it on first use."""
    scratch = context.scratch
    if scratch is None:
        # No active session scratch (shouldn't happen during a command); use a
        # throwaway so a single call still resolves its own freshly-laid tables.
        return {"ranges": [], "next": 1}
    reg = scratch.get("ztables")
    if reg is None:
        reg = {"ranges": [], "next": 1}
        scratch["ztables"] = reg
    return reg


def addr_of(table):
    """Normalise a table value to a base address (int).  A list is laid out at
    a fresh non-overlapping range on first encounter (deduped by identity); an
    int is already an address; anything else is null (0)."""
    if isinstance(table, int):
        return table
    if not isinstance(table, list):
        return 0
    reg = reg_lookup()
    for entry in reg["ranges"]:
        if entry[2] is table:
            return entry[0]
    base = reg["next"]
    width = len(table) if len(table) > 0 else 1
    extent = width + 16  # pad so in-place growth can't run into the next table
    reg["ranges"].append([base, base + extent, table])
    reg["next"] = base + extent
    return base


def resolve_addr(address):
    """Map an int address to ``(backing_list, offset)`` or ``(None, 0)``."""
    if not isinstance(address, int) or address <= 0:
        return (None, 0)
    for entry in reg_lookup()["ranges"]:
        if entry[0] <= address < entry[1]:
            return (entry[2], address - entry[0])
    return (None, 0)


if verb_name == "zaddr_rest":
    # <REST tbl byte_offset> — a pointer `byte_offset` cells into tbl.
    tbl = args[0] if args else None
    offset = args[1] if len(args) > 1 else 2
    return addr_of(tbl) + (offset or 0)

if verb_name == "zaddr_get":
    # <GET/GETB ptr i> — read cell i past the pointer.
    addr = args[0] if args else None
    idx = args[1] if len(args) > 1 else 0
    lst, off = resolve_addr(addr_of(addr))
    if lst is None:
        return 0
    pos = off + (idx or 0)
    if 0 <= pos < len(lst):
        value = lst[pos]
        return value if value is not None else 0
    return 0

if verb_name == "zaddr_put":
    # <PUT/PUTB ptr i v> — write cell i past the pointer, in place.
    addr = args[0] if args else None
    idx = args[1] if len(args) > 1 else 0
    val = args[2] if len(args) > 2 else 0
    lst, off = resolve_addr(addr_of(addr))
    if lst is None:
        return val
    pos = off + (idx or 0)
    if pos < 0:
        return val
    while len(lst) <= pos:
        lst.append(0)
    lst[pos] = val
    return val

if verb_name == "zaddr_copyt":
    # <COPYT src dest count> — Z-machine ``copy_table`` semantics:
    #   * dest == 0  → zero ``count`` cells at src (table-clear form).
    #   * count > 0  → *safe* copy: choose the direction that avoids corruption
    #                  when src/dest overlap in the same backing table (forward
    #                  when dest <= src, backward when dest > src) — like memmove.
    #   * count < 0  → forced *forward* copy of abs(count) cells, even when that
    #                  corrupts (deliberate fill — e.g. SETUP-DBOX propagating a
    #                  single SP through the whole box to clear it).
    src = args[0] if args else None
    dest = args[1] if len(args) > 1 else None
    count = int(args[2]) if len(args) > 2 and args[2] is not None else 0
    src_addr = addr_of(src)
    slst, soff = resolve_addr(src_addr)
    if slst is None:
        return None
    span = abs(count)
    if dest == 0:
        # Zero `span` cells at src.
        for k in range(span):
            pos = soff + k
            if 0 <= pos < len(slst):
                slst[pos] = 0
        return None
    dest_addr = addr_of(dest)
    dlst, doff = resolve_addr(dest_addr)
    if dlst is None:
        return None
    if count < 0:
        order = range(span)  # forced forward (fill / deliberate overlap)
    elif dlst is slst and dest_addr > src_addr:
        order = range(span - 1, -1, -1)  # overlap shifting up → copy backward
    else:
        order = range(span)  # forward is safe (no overlap, or shifting down)
    for k in order:
        spos = soff + k
        dpos = doff + k
        cell = slst[spos] if 0 <= spos < len(slst) else 0
        if dpos < 0:
            continue
        while len(dlst) <= dpos:
            dlst.append(0)
        dlst[dpos] = cell
    return None

if verb_name == "zaddr_intbl_p":
    # <INTBL? value table length [record-size]> — search `length` cells of
    # `table` for `value`, stepping `record-size` cells (default 1).  Returns
    # the int address of the match (so callers can REST / diff from it) or 0.
    value = args[0] if args else None
    addr = args[1] if len(args) > 1 else None
    length = args[2] if len(args) > 2 else None
    stride = args[3] if len(args) > 3 else 1
    start = addr_of(addr)
    lst, off = resolve_addr(start)
    if lst is None:
        return 0
    stride = int(stride or 1)
    if stride < 1:
        stride = 1
    limit = len(lst) - off if length is None else int(length)
    k = 0
    while k < limit and (off + k) < len(lst):
        if lst[off + k] == value:
            return start + k
        k += stride
    return 0
