#!moo verb version --on "Zork Actor" --dspec none
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Hand-written replacement for V-VERSION.

The auto-translated body emits ``print(chr(table_get(...)), end='')`` once
per serial-number digit inside a ``while`` loop.  Each ``print`` call is a
separate writer event for the raw-mode shell, which appends ``\\n`` per
event — turning "820424" into one digit per line.  Buffering the digits
into a single string before printing avoids that.

The release number and serial table live on the System Object as
``zstate_version_table`` (a list of integers).  Slots 1-23 are filled by
the converter from the ZIL ``<TABLE> ,V-VERSION ...`` form.
"""

from moo.sdk import context

print(
    "ZORK I: The Great Underground Empire\n"
    "\n"
    "Infocom interactive fiction - a fantasy story\n"
    "\n"
    "Copyright (c) 1981, 1982, 1983, 1984, 1985, 1986 Infocom, Inc. All rights reserved.\n"
    "ZORK is a registered trademark of Infocom, Inc.\n"
)

table = _.get_property("zstate_version_table")
release = (_.table_get(table, 1) or 0) & (context.player.zstate_get("*3777*") or 0)
serial_chars = []
for cnt in range(18, 24):
    code = _.table_get(table, cnt)
    if code is None:
        continue
    serial_chars.append(chr(code))
serial = "".join(serial_chars)

print(f"Release {release} / Serial number {serial}")
