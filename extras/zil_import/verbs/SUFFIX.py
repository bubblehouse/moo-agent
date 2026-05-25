#!moo verb SUFFIX --on "Actor" --dspec either

# pylint: disable=return-outside-function,undefined-variable,no-name-in-module

"""
Set output suffix marker for machine parsing.

Usage:
    SUFFIX <marker>     Set suffix to the specified marker string
    SUFFIX              Show current suffix setting
    SUFFIX clear        Clear the suffix

The SUFFIX command sets a marker string that will be emitted after each
command's output. This is intended for use by machine clients that need to
reliably parse command output without relying on prompt detection or timeouts.

The suffix is session-specific and will be cleared when you disconnect.

Example:
    SUFFIX >>MOO-END<<
    look
    The Laboratory(#3)
    ...
    >>MOO-END<<

See also: PREFIX, a11y
"""

from moo.sdk import get_session_setting, set_session_setting, context

# Get the marker from dobj string if provided
if context.parser.has_dobj_str():
    marker = context.parser.get_dobj_str()

    if marker.lower() == "clear":
        # Clear the suffix
        set_session_setting("output_suffix", None)
        print("Output suffix cleared")
    else:
        # Set the suffix
        set_session_setting("output_suffix", marker)
        print(f"Output suffix set to: {marker}")
else:
    # Show current setting
    suffix = get_session_setting("output_suffix")
    if suffix:
        print(f"Current output suffix: {suffix}")
    else:
        print("No output suffix set")
