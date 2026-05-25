#!moo verb dig --on "Thing" --dspec this
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Hand-written V-DIG replacement.

The auto-emitted body unconditionally formats the missing-iobj branch as
``"Digging with a " + prsi.desc() + " is silly."``, which prints
"Digging with a  is silly." (double space, empty tool name) when the
player types bare ``dig sand``.  Canonical Zork prints
"With your bare hands?" for the no-tool case.
"""

from moo.sdk import NoSuchObjectError, context, lookup

parser = context.parser
try:
    prsi = parser.get_iobj() if parser.has_iobj() else None
except NoSuchObjectError:
    prsi = None

if prsi is None:
    print("Digging with your bare hands is, by all accounts, inadvisable.")
    return True
if prsi == lookup("shovel"):
    print("There's no reason to be digging here.")
    return True
if prsi.flag("toolbit"):
    print("Digging with the " + prsi.desc() + " is slow and tedious.")
    return True
print("Digging with a " + prsi.desc() + " is silly.")
return True
