#!moo verb flag set_flag getp --on "Root"
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
    # A ``P?`` *property number* (XZIP/Beyond Zork exit-table routines reach a
    # room's exit property via ``<GETP rm <P?-number>>``, where the number
    # comes from PDIR-LIST or a direction loop variable).  Resolve it to the
    # direction property name via the seeded reverse map.  EZIP games always
    # pass string names, so this branch is inert for them.
    if isinstance(name, int):
        try:
            pnum_to_dir = _.get_property("zstate_pnum_to_dir")
        except NoSuchPropertyError:
            pnum_to_dir = None
        if pnum_to_dir and 0 <= name < len(pnum_to_dir) and pnum_to_dir[name]:
            name = pnum_to_dir[name]
        else:
            return default
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
