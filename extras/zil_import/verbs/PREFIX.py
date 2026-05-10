#!moo verb PREFIX --on "Zork Actor" --dspec either

# pylint: disable=return-outside-function,undefined-variable,no-name-in-module

"""
Set output prefix marker for machine parsing.

Usage:
    PREFIX <marker>     Set prefix to the specified marker string
    PREFIX              Show current prefix setting
    PREFIX clear        Clear the prefix

The PREFIX command sets a marker string that will be emitted before each
command's output. This is intended for use by machine clients that need to
reliably parse command output without relying on prompt detection or timeouts.

The prefix is session-specific and will be cleared when you disconnect.

Example:
    PREFIX >>MOO-START<<
    look
    >>MOO-START<<
    The Laboratory(#3)
    ...

See also: SUFFIX, a11y
"""

from moo.sdk import get_session_setting, set_session_setting, context

# Get the marker from dobj string if provided
if context.parser.has_dobj_str():
    marker = context.parser.get_dobj_str()

    if marker.lower() == "clear":
        # Clear the prefix
        set_session_setting("output_prefix", None)
        print("Output prefix cleared")
    else:
        # Set the prefix
        set_session_setting("output_prefix", marker)
        print(f"Output prefix set to: {marker}")
else:
    # Show current setting
    prefix = get_session_setting("output_prefix")
    if prefix:
        print(f"Current output prefix: {prefix}")
    else:
        print("No output prefix set")
