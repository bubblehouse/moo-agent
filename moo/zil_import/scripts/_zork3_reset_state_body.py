# Reset Zork III world state to canonical opening positions.
#
# Two callers (mirrors the zork1 / zork2 reset bodies):
#   1. moo_init --bootstrap zork3 [--sync] — generator.py copies this file
#      to moo/bootstrap/zork3/099_reset_state.py so it runs after rooms /
#      objects / exits are loaded.
#   2. moo/zil_import/scripts/zork3_smoke.py — reads this file's text and
#      passes it to `manage.py shell -c` before the smoke walks the opening.
#
# Minimal first-pass reset: snapshot capture/restore (wipes session
# pollution) + park the Adventurer at the canonical start (Endless Stair,
# ZIL ZORK2-STAIR, set by GO via <SETG HERE ,ZORK2-STAIR>) + basic zstate
# + the substrate property-grant loop.  Per-object canonical-position
# seeding gets added here as shakedown surfaces the need.  Idempotent.
# Hardcodes ``zork3.local``.
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
    print(f"zork3 reset: captured snapshot to {snapshot_path} ({len(objects_data)} objects)")


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
    print(f"zork3 reset: restored snapshot from {snapshot_path}")


def _reset_zork3_world(site):
    """Apply the canonical world-state reset against ``site``.

    Wrapped in a function so this file is safe to ``exec`` during the
    bootstrap pass too: when first-time ``moo_init`` doesn't yet have a
    ``zork3.local`` Site row, the dispatch below skips this call entirely.
    """
    # Every Object.save() below dispatches the 'accept' verb on the new
    # location, which needs the active site set on the ContextManager.
    ContextManager.set_site(site)

    # Capture-or-restore snapshot of object positions / properties.  First
    # call after a fresh sync captures the clean post-bootstrap state;
    # subsequent calls restore it, wiping session pollution.
    snapshot_path = _SNAPSHOT_DIR / f"zork3-site-{site.pk}.json"
    try:
        if snapshot_path.exists():
            _snapshot_restore(snapshot_path, site)
        else:
            _snapshot_capture(site, "zork3", snapshot_path)
    except _SnapshotSiteMismatch as exc:
        print(f"zork3 reset: snapshot site mismatch, skipping restore: {exc}")
    except Exception as exc:  # pylint: disable=broad-except
        print(f"zork3 reset: snapshot {type(exc).__name__}: {exc}")

    # Gameplay runs through the non-wizard Adventurer avatar (real ACL
    # enforcement).  Zork III opens on the Endless Stair (ZIL ZORK2-STAIR,
    # set by GO via <SETG HERE ,ZORK2-STAIR>), carrying nothing.
    adventurer = Object.global_objects.get(name="Adventurer", site=site)
    start = Object.global_objects.get(name="Endless Stair", site=site)

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
    print("zork3 reset")


# When this file runs as part of the bootstrap (first-time moo_init), the
# zork3.local Site row may not yet exist — skip silently so the loader can
# proceed; the next --sync (after the site is created) runs the reset.
_site = Site.objects.filter(domain="zork3.local").first()
if _site is None:
    print("zork3 reset: site not yet created, skipping")
else:
    _reset_zork3_world(_site)
