#!moo verb flag set_flag getp --on "Zork Root"
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Property/flag helpers for ZIL game objects.

flag:     args[0] = property name → bool (False if missing)
set_flag: args[0] = property name, args[1] = value
getp:     args[0] = property name [, args[1] = default]
          ZIL's ``<GETP obj prop>`` returns 0 for missing properties; this
          helper lets translated code avoid ``NoSuchPropertyError``.

``obvious`` is intrinsic on Object (a model field, not a Property), so
both reads and writes route through attribute access.

Translated routines call these as methods on the target object, e.g.
``obj.flag("openable")``, ``obj.set_flag("obvious", True)``,
``obj.getp("strength")``.
"""

from moo.sdk import NoSuchPropertyError

if verb_name == "set_flag":
    name = args[0]
    value = bool(args[1])
    if name == "obvious":
        this.obvious = value
        this.save()
    elif name == "invisible":
        # INVISIBLE hides the object from the parser entirely.  This
        # translates to ``obvious=not value`` on the intrinsic field
        # (which the parser's dobj search consults) AND a stored
        # ``invisible`` property so translated routines that read the
        # flag get the same answer they wrote.  NDESCBIT is a separate
        # flag (``ndescbit`` property) and is not touched here.
        this.obvious = not value
        this.save()
        this.set_property(name, value)
    else:
        this.set_property(name, value)
elif verb_name == "getp":
    name = args[0]
    default = args[1] if len(args) > 1 else None
    if name == "obvious":
        return this.obvious
    try:
        return this.get_property(name)
    except NoSuchPropertyError:
        return default
else:
    name = args[0]
    if name == "obvious":
        return bool(this.obvious)
    try:
        return bool(this.get_property(name))
    except NoSuchPropertyError:
        return False
