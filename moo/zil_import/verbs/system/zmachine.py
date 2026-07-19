#!moo verb lowcore --on "System Object"
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""Z-machine header reads (``<LOWCORE field>``).

The Z-machine's ``LOWCORE`` op reads a field from the story-file header (Flags,
interpreter id/version, screen geometry, serial number, …).  DjangoMOO runs the
translated routines directly with no story file, so there is no header to read.

Return the benign baseline (``0``) for every field.  In practice ``LOWCORE`` is
only reached on paths the seeded reset state doesn't already cover:
- ``<LOWCORE FLAGS>`` capability bit-tests — 0 means "no special interpreter
  capability", the safe default (e.g. V-LOOK's ``<BTST <LOWCORE FLAGS> 1>``
  then skips a redundant re-describe).
- ``<LOWCORE INTID/INTVR/ZORKID/SERIAL>`` in V-VERSION — cosmetic banner data,
  not on the gameplay path.
Screen geometry (``FWRD``/``HWRD``/``VWRD``) is normally read here by INITVARS,
but the reset body seeds WIDTH/HEIGHT/CWIDTH/… directly instead of running it.
"""

return 0
