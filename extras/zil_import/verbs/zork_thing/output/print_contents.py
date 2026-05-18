#!moo verb print_contents --on "Zork Thing" --dspec this
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Hand-written PRINT-CONTENTS replacement.

Returns a string listing of the object's direct contents (vowel-aware
articles, ``and`` before the last item).  Returning instead of printing
lets the caller include the listing in its own ``print(...)`` call so
the open-container reveal sentence stays intact — printing from a
sub-verb would flush before the caller's outer ``print(...)`` due to
the per-verb ``_print_`` collector.
"""

from moo.sdk import task_time_low

obj = args[0] if len(args) > 0 else None
f = 0
n = 0
v_1st_p = True
it_p = 0
two_p = 0
parts = []


def article_for(name):
    return "an " if name[:1].lower() in ("a", "e", "i", "o", "u") else "a "


if f := obj.contents.first():
    while True:
        if task_time_low():
            return "[zil] long-running loop in PRINT-CONTENTS; aborting (bug — please report)."
        n = _.next_sibling(f)
        if v_1st_p:
            v_1st_p = False
        else:
            parts.append(", ")
            if not n:
                parts.append("and ")
        parts.append(article_for(f.desc()) + f.desc())
        if not it_p and not two_p:
            it_p = f
        else:
            two_p = True
            it_p = False
        f = n
        if not f:
            if it_p and not two_p:
                _.zork_thing.this_is_it(it_p)
            return "".join(parts)
return ""
