#!moo verb print_contents --on "Zork Thing" --dspec this
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Hand-written PRINT-CONTENTS replacement.

Mirrors the canonical ZIL routine but replaces the hardcoded ``"a "``
literal with a vowel-aware article so ``open egg`` reveals
``an ancient map`` rather than ``a ancient map``.
"""

from moo.sdk import task_time_low

obj = args[0] if len(args) > 0 else None
f = 0
n = 0
v_1st_p = True
it_p = 0
two_p = 0


def article_for(name):
    return "an " if name[:1].lower() in ("a", "e", "i", "o", "u") else "a "


if f := obj.contents.first():
    while True:
        if task_time_low():
            print("[zil] long-running loop in PRINT-CONTENTS; aborting (bug — please report).")
            return False
        n = _.next_sibling(f)
        if v_1st_p:
            v_1st_p = False
        else:
            print(", ", end="")
            if not n:
                print("and ", end="")
        print(article_for(f.desc()) + f.desc(), end="")
        if not it_p and not two_p:
            it_p = f
        else:
            two_p = True
            it_p = False
        f = n
        if not f:
            if it_p and not two_p:
                _.zork_thing.this_is_it(it_p)
            return True
