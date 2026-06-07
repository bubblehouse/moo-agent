# Reset Beyond Zork world state to canonical opening positions.
#
# Two callers (mirrors the zork1 / zork2 / zork3 reset bodies):
#   1. moo_init --bootstrap beyondzork [--sync] — generator.py copies this
#      file to moo/bootstrap/beyondzork/099_reset_state.py so it runs after
#      rooms / objects / exits are loaded.
#   2. a future beyondzork smoke script — reads this file's text and passes
#      it to `manage.py shell -c` before driving the opening.
#
# Minimal first-pass reset: snapshot capture/restore (wipes session
# pollution) + park the Adventurer at the canonical start (Hilltop, set by
# GO via <SETG HERE ,HILLTOP> in misc.zil) + basic zstate + the substrate
# property-grant loop.  Beyond Zork's RPG layer (character stats, the
# split-screen auto-map) is NOT seeded here yet — that arrives as the port
# matures.  Idempotent.  Hardcodes ``beyondzork.local``.
import datetime as _dt
import json as _json
from pathlib import Path

from django.contrib.sites.models import Site
from moo.core.code import ContextManager
from moo.core.models.acl import Access, _get_permission_id
from moo.core.models.auth import Player
from moo.core.models.object import Object
from moo.core.models.property import Property

_SNAPSHOT_DIR = Path("/usr/app/snapshots")


class _SnapshotSiteMismatch(RuntimeError):
    """Snapshot's recorded site doesn't match the site argument."""


def _snapshot_serialize_value(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, list):
        return [_snapshot_serialize_value(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _snapshot_serialize_value(v) for k, v in value.items()}
    pk = getattr(value, "pk", None)
    if pk is not None and value.__class__.__name__ == "Object":
        return {"__obj__": pk}
    return repr(value)


def _snapshot_deserialize_value(value, object_by_pk):
    if isinstance(value, dict) and set(value.keys()) == {"__obj__"}:
        return object_by_pk.get(value["__obj__"])
    if isinstance(value, list):
        return [_snapshot_deserialize_value(v, object_by_pk) for v in value]
    if isinstance(value, dict):
        return {k: _snapshot_deserialize_value(v, object_by_pk) for k, v in value.items()}
    return value


def _snapshot_capture(site, repo, snapshot_path):
    """Capture every Object on ``site`` to ``snapshot_path`` as JSON."""
    objects_qs = Object.global_objects.filter(site=site).prefetch_related("properties")
    objects_data = []
    for obj in objects_qs:
        props = {}
        for prop in obj.properties.all():
            try:
                props[prop.name] = _snapshot_serialize_value(prop.value)
            except Exception:  # pylint: disable=broad-except
                props[prop.name] = None
        objects_data.append(
            {
                "pk": obj.pk,
                "name": obj.name,
                "location_pk": obj.location_id,
                "obvious": bool(obj.obvious),
                "properties": props,
            }
        )
    payload = {
        "site_pk": site.pk,
        "site_domain": site.domain,
        "bootstrap_repo": repo,
        "captured_at": _dt.datetime.now(_dt.UTC).isoformat(),
        "object_count": len(objects_data),
        "objects": objects_data,
    }
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(_json.dumps(payload, indent=2, sort_keys=True))
    print(f"beyondzork reset: captured snapshot to {snapshot_path} ({len(objects_data)} objects)")


def _snapshot_restore(snapshot_path, site):
    """Restore snapshot onto ``site`` after re-asserting site identity."""
    data = _json.loads(snapshot_path.read_text())
    if data.get("site_pk") != site.pk:
        raise _SnapshotSiteMismatch(
            f"snapshot site_pk={data.get('site_pk')} (domain={data.get('site_domain')!r}) "
            f"vs active site pk={site.pk} (domain={site.domain!r}); refusing restore"
        )
    if data.get("site_domain") != site.domain:
        raise _SnapshotSiteMismatch(
            f"snapshot site_domain={data.get('site_domain')!r} vs active {site.domain!r}; refusing restore"
        )
    existing = {obj.pk: obj for obj in Object.global_objects.filter(site=site)}
    object_by_pk = dict(existing)
    location_updates = []
    for entry in data["objects"]:
        obj = existing.get(entry["pk"])
        if obj is None:
            continue
        new_loc_pk = entry.get("location_pk")
        new_obvious = bool(entry.get("obvious", True))
        if obj.location_id != new_loc_pk or bool(obj.obvious) != new_obvious:
            obj.location_id = new_loc_pk
            obj.obvious = new_obvious
            location_updates.append(obj)
    if location_updates:
        Object.global_objects.bulk_update(location_updates, ["location", "obvious"])
    for entry in data["objects"]:
        obj = existing.get(entry["pk"])
        if obj is None:
            continue
        live_props = {p.name: p for p in obj.properties.all()}
        for name, raw_value in entry.get("properties", {}).items():
            value = _snapshot_deserialize_value(raw_value, object_by_pk)
            prop = live_props.get(name)
            if prop is None:
                obj.set_property(name, value)
            else:
                if prop.value != value:
                    prop.value = value
                    prop.save(update_fields=["value"])
    print(f"beyondzork reset: restored snapshot from {snapshot_path}")


def _reset_beyondzork_world(site):
    """Apply the canonical world-state reset against ``site``.

    Wrapped in a function so this file is safe to ``exec`` during the
    bootstrap pass too: when first-time ``moo_init`` doesn't yet have a
    ``beyondzork.local`` Site row, the dispatch below skips this call
    entirely.
    """
    # Every Object.save() below dispatches the 'accept' verb on the new
    # location, which needs the active site set on the ContextManager.
    ContextManager.set_site(site)

    # Capture-or-restore snapshot of object positions / properties.  First
    # call after a fresh sync captures the clean post-bootstrap state;
    # subsequent calls restore it, wiping session pollution.
    snapshot_path = _SNAPSHOT_DIR / f"beyondzork-site-{site.pk}.json"
    try:
        if snapshot_path.exists():
            _snapshot_restore(snapshot_path, site)
        else:
            _snapshot_capture(site, "beyondzork", snapshot_path)
    except _SnapshotSiteMismatch as exc:
        print(f"beyondzork reset: snapshot site mismatch, skipping restore: {exc}")
    except Exception as exc:  # pylint: disable=broad-except
        print(f"beyondzork reset: snapshot {type(exc).__name__}: {exc}")

    # Gameplay runs through the non-wizard Adventurer avatar (real ACL
    # enforcement).  Beyond Zork opens on the Hilltop (ZIL HILLTOP, set by
    # GO via <SETG HERE ,HILLTOP> in misc.zil), carrying nothing.
    adventurer = Object.global_objects.get(name="Adventurer", site=site)
    start = Object.global_objects.get(name="Hilltop", site=site)

    # Clear daemon queue + turn counter + GO-ran flag so a previous run's
    # stale state doesn't carry over.
    adventurer.set_property("zstate_queue", [])
    adventurer.set_property("zstate_drop", [])
    adventurer.set_property("zstate_moves", 0)
    adventurer.set_property("zstate_started", False)
    adventurer.set_property("zstate_deaths", 0)
    adventurer.set_property("zstate_score", 0)
    adventurer.set_property("zstate_base_score", 0)
    # Short-circuit lit? — the ZIL lit? routine walks parser-internal tables
    # we don't initialise, so calls from goto() can crash.  ALWAYS-LIT is
    # read first in lit? and returns True without touching those tables.
    adventurer.set_property("zstate_always_lit", True)
    # describe_room reads the *cached* LIT zstate directly (not the is_lit
    # predicate), so seed it True too — otherwise the very first `look`
    # before any turn-recompute reports "It is pitch black."
    adventurer.set_property("zstate_lit", True)
    # WINNER's STRENGTH defaults to 0 in ZIL; arithmetic in combat routines
    # requires the property to exist so .getp("strength") returns 0 not None.
    adventurer.set_property("strength", 0)
    adventurer.location = start
    adventurer.save()

    # Death routines read ``player_start`` off the System Object to teleport
    # the player back after a lethal hit.  Seed it to the opening room.
    system_object = Object.global_objects.get(name="System Object", site=site)
    system_object.set_property("player_start", start)
    system_object.save()

    # ``P?<dir>`` direction property-number constants.  Beyond Zork is a v5
    # game whose ZIL compiler assigns each direction property a number; routines
    # like MARK-EXITS iterate them numerically (``<SET DIR ,P?NORTH>`` …
    # ``<DLESS? DIR ,P?DOWN>``) and fetch a room's exit table via
    # ``<GETP ,HERE DIR>``.  These are compiler-intrinsic (not in the source as
    # CONSTANTs), so seed them as consecutive descending integers — NORTH
    # highest, DOWN lowest of the mapped range — so the decrement loop visits
    # each compass/vertical direction once and IN/OUT fall below P?DOWN (the
    # map loop skips them).  ``zstate_get("P?NORTH")`` reads ``zstate_p_north``.
    _pdir_numbers = {
        "north": 12,
        "ne": 11,
        "east": 10,
        "se": 9,
        "south": 8,
        "sw": 7,
        "west": 6,
        "nw": 5,
        "up": 4,
        "down": 3,
        "in": 2,
        "out": 1,
    }
    for _dname, _dnum in _pdir_numbers.items():
        system_object.set_property("zstate_p_" + _dname, _dnum)
    system_object.save()

    # Runtime display geometry.  Beyond Zork's INITVARS / SETUP-CHARACTER
    # compute these from the Z-machine screen-model header (CWIDTH/CHEIGHT in
    # pixels, WIDTH/HEIGHT in cells) — there is no Z-machine here, so seed
    # cell-matched values directly.  CWIDTH = CHEIGHT = 1 puts DO-CURSET into
    # its cell-addressed branch (``window_cursor(row, col)`` straight through).
    # The derived widths mirror the INITVARS arithmetic so the map/status-line
    # math produces the same positive extents the game expects.
    _mwidth = 17  # MWIDTH constant
    _screen_width = 80
    _screen_height = 24
    _normal_dheight = 9  # NORMAL-DHEIGHT constant
    _statmax = 99  # STATMAX constant
    _label_width = 12  # LABEL-WIDTH constant
    _bar_res = 8
    _swidth = (_statmax // _bar_res) + 1
    _dwidth = _screen_width - (_mwidth + 3)
    _display_geometry = {
        "CWIDTH": 1,
        "CHEIGHT": 1,
        "WIDTH": _screen_width,
        "HEIGHT": _screen_height,
        "DWIDTH": _dwidth,
        "BOXWIDTH": _dwidth,
        "MAX-DHEIGHT": _normal_dheight,
        "DHEIGHT": _normal_dheight,
        "MOUSEDGE": (_screen_width - _mwidth) - 1,
        "BAR-RES": _bar_res,
        "SWIDTH": _swidth,
        "BARWIDTH": _label_width + _swidth + 5,
        "VT220": True,
        "VT100": False,
        "PRIOR": 0,
        "HOST": 0,  # neutral interpreter id — avoids the Apple/Mac/IBM paths
        # Routine VALUES (XZIP routine-value translation = the routine name).
        # INITVARS sets these; DRAW-MAP does <APPLY ,MAP-ROUTINE …> and the
        # stats line <APPLY ,STAT-ROUTINE …>.  CLOSE-MAP draws the close (font-3)
        # auto-map; RAWBAR paints the stat bargraphs.
        "MAP-ROUTINE": "close_map",
        "STAT-ROUTINE": "rawbar",
        # NEW-MAP skips the redraw when <NOT <ZERO? ,SAME-COORDS>>; an unseeded
        # None reads as non-zero, so seed 0 so the first look actually draws.
        "SAME-COORDS": 0,
        # DISPLAY-PLACE diffs against the previously-mapped room; 0 = none yet.
        "OLD-HERE": 0,
        # No pending walk direction on a fresh look — DISPLAY-PLACE's
        # <NOT ,P-WALK-DIR> takes the NEW-MAP (full redraw) branch only when
        # this is falsy; an unseeded None misses the `in (False, …)` test.
        "P-WALK-DIR": 0,
    }
    for _gname, _gval in _display_geometry.items():
        _slot = "zstate_" + _gname.lower().replace("-", "_")
        system_object.set_property(_slot, _gval)

    # Box-drawing glyphs.  The ZIL constants hold IBM CP437 codepoints
    # (IBM-TLC = 218 …); ``chr(218)`` is Latin-1 'Ú', not a corner.  Remap to
    # the Unicode box-drawing block so the auto-map frame paints as a real box
    # through the same Rich text pipeline (font 3 → Unicode, per the feasibility
    # assessment).
    _box_glyphs = {
        "IBM-TLC": 0x250C,  # ┌
        "IBM-TRC": 0x2510,  # ┐
        "IBM-BLC": 0x2514,  # └
        "IBM-BRC": 0x2518,  # ┘
        "IBM-HORZ": 0x2500,  # ─
        "IBM-VERT": 0x2502,  # │
    }
    for _gname, _gval in _box_glyphs.items():
        system_object.set_property("zstate_" + _gname.lower().replace("-", "_"), _gval)
    system_object.save()

    # Park every connected avatar at the opening room.
    for _player_record in Player.objects.filter(site=site, avatar__isnull=False):  # pylint: disable=no-member
        _avatar = _player_record.avatar
        _avatar.location = start
        _avatar.save()

    # Property-level write grants.  set_property on an existing Property row
    # requires `write` on the Property itself.  Cover every Property of every
    # substrate-classed instance with `everyone:write` so the Adventurer can
    # mutate world state at runtime.  Idempotent via get_or_create.
    _write_id = _get_permission_id("write")
    _substrate_class_names = ("Thing", "Container", "Room", "Actor NPC")
    _substrate_objects_qs = Object.global_objects.filter(
        site=site,
        parents__name__in=_substrate_class_names,
    ).distinct()
    for _prop in Property.objects.filter(origin__in=_substrate_objects_qs):  # pylint: disable=no-member
        Access.objects.get_or_create(  # pylint: disable=no-member
            property=_prop,
            rule="allow",
            permission_id=_write_id,
            type="group",
            group="everyone",
        )
    print("beyondzork reset")


# When this file runs as part of the bootstrap (first-time moo_init), the
# beyondzork.local Site row may not yet exist — skip silently so the loader
# can proceed; the next --sync (after the site is created) runs the reset.
_site = Site.objects.filter(domain="beyondzork.local").first()
if _site is None:
    print("beyondzork reset: site not yet created, skipping")
else:
    _reset_beyondzork_world(_site)
