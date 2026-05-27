#!moo verb rehydrate_preps dehydrate_preps --on "System Object"
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Pre-dispatch helpers for the ZIL ``again`` / ``g`` snapshot in ``do_command``.

The parser's ``prepositions`` dict holds Object references that can't be
serialized into ``zstate_last_command`` directly.  These two verbs convert
between the live form (``[spec, str, Object]``) and the stored form
(``[spec, str, pk]``) so the snapshot survives a round-trip through a
property.

:param args[0]: ``rehydrate_preps`` — stored dict
    ``{prep: [[spec, str, pk_or_None], ...]}``;
    ``dehydrate_preps`` — live dict
    ``{prep: [[spec, str, Object_or_None], ...]}``.
:returns: The same shape with pks resolved to Objects (rehydrate) or
    Objects converted to pks (dehydrate).
"""

from moo.sdk import lookup, NoSuchObjectError

if verb_name == "rehydrate_preps":
    preps_data = args[0] if args else {}
    out = {}
    for prep, recs in preps_data.items():
        rec_list = []
        for rec in recs:
            spec, obj_str, pk = rec[0], rec[1], rec[2]
            obj = None
            if pk is not None:
                try:
                    obj = lookup(int(pk))
                except NoSuchObjectError:
                    obj = None
            rec_list.append([spec, obj_str, obj])
        out[prep] = rec_list
    return out

if verb_name == "dehydrate_preps":
    preps = args[0] if args else {}
    out = {}
    for prep, recs in preps.items():
        rec_list = []
        for rec in recs:
            spec, obj_str, obj = rec[0], rec[1], rec[2]
            pk = obj.pk if obj is not None else None
            rec_list.append([spec, obj_str, pk])
        out[prep] = rec_list
    return out
