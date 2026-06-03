#!moo verb zatom --on "System Object"
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Resolve a ZIL object-constant atom (e.g. ``,SWITCH``) to its Object.

A ZIL ``,FOO`` reference always means "the object the author named FOO",
but a plain ``lookup("foo")`` matches name OR alias and returns the
lowest-PK hit — so when a *different* object carries ``foo`` as a SYNONYM
the wrong object wins (HHG: the Galley dipswitches and the Hold case-switch
both alias ``switch``, shadowing the generator SWITCH).  The bootstrap
records the authoritative atom->PK map in ``zatom_pk_map`` (set by
``030_objects.py``); consult it first, fall back to the alias lookup when
the atom is absent (older bootstrap) or the object was recycled.

The translator only routes an atom through here when its slug is known to
collide with another object's name/alias; non-ambiguous atoms keep the
plain ``lookup(...)`` form.

:param args[0]: The ZIL atom in UPPER-KEBAB-CASE (e.g. ``"SWITCH"``).
:returns: The Object the atom names.
"""

from moo.sdk import lookup, NoSuchObjectError, NoSuchPropertyError

atom = args[0]
try:
    atom_pk_map = this.get_property("zatom_pk_map") or {}
except NoSuchPropertyError:
    atom_pk_map = {}
pk = atom_pk_map.get(atom)
if pk is not None:
    try:
        return lookup(int(pk))
    except NoSuchObjectError:
        pass
return lookup(atom.lower().replace("-", "_"))
