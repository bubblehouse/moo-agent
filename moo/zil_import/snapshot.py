"""
Snapshot capture and restore for ZIL-bootstrapped sites.

Eliminates the cross-session pollution problem from interactive
shakedown: each play-through mutates object locations, daemon
counters, NPC flags. Without a snapshot, ``--reset`` only re-places
the avatar — every other object stays where the prior session left it
(gown stuck in Vogon Hold, satchel still on the panel, daemon
counters past their fire points).

Scope (per design discussion 2026-05-25):
  - Objects: every ``Object`` on the target site, with location_pk
  - Properties: every Property row, capturing name/value
  - Flags: stored as properties (see ``ir.FLAG_PROPERTIES``)
  - NOT captured: ACLs, Verbs, Aliases (set at bootstrap and not
    mutated during gameplay)

Safety:
  - Both capture and restore take an explicit ``site`` argument.
  - Restore re-confirms ``snapshot["site_pk"]`` and ``site_domain``
    match the active site before any write.  Wrong-site mismatch
    raises ``SnapshotSiteMismatch`` — no DB write happens.
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Any


class SnapshotSiteMismatch(RuntimeError):
    """Snapshot's recorded site doesn't match the site argument."""


def _serialize_value(value: Any) -> Any:
    """
    Round-trip a property value through JSON.

    Object references are serialized as ``{"__obj__": pk}`` so restore
    can re-resolve. Primitive scalars / lists / dicts pass through.
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, list):
        return [_serialize_value(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _serialize_value(v) for k, v in value.items()}
    pk = getattr(value, "pk", None)
    if pk is not None and value.__class__.__name__ == "Object":
        return {"__obj__": pk}
    return repr(value)


def _deserialize_value(value: Any, object_by_pk: dict[int, Any]) -> Any:
    if isinstance(value, dict) and set(value.keys()) == {"__obj__"}:
        return object_by_pk.get(value["__obj__"])
    if isinstance(value, list):
        return [_deserialize_value(v, object_by_pk) for v in value]
    if isinstance(value, dict):
        return {k: _deserialize_value(v, object_by_pk) for k, v in value.items()}
    return value


def capture_snapshot(site, repo: str, snapshot_path: Path) -> Path:
    """
    Capture every Object on ``site`` to ``snapshot_path`` as JSON.

    :param site: Active ``django.contrib.sites.models.Site``. Used to
        scope the Object query and recorded in the file header.
    :param repo: Dataset name (``"zork1"``, ``"hhg"``) — recorded so a
        restore can warn on dataset mismatch.
    :param snapshot_path: Destination JSON file. Parent dir is created
        on demand.
    """
    from moo.core.models.object import Object
    from moo.core.models.property import Property

    objects_qs = Object.global_objects.filter(site=site).prefetch_related("properties")
    objects_data: list[dict[str, Any]] = []
    for obj in objects_qs:
        props: dict[str, Any] = {}
        for prop in obj.properties.all():
            try:
                props[prop.name] = _serialize_value(prop.value)
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
    snapshot_path.write_text(json.dumps(payload, indent=2, sort_keys=True))
    return snapshot_path


def _assert_site_matches(snapshot_data: dict, site) -> None:
    if snapshot_data.get("site_pk") != site.pk:
        raise SnapshotSiteMismatch(
            f"Snapshot site_pk={snapshot_data.get('site_pk')} "
            f"(domain={snapshot_data.get('site_domain')!r}) "
            f"does not match active site pk={site.pk} (domain={site.domain!r}). "
            "Refusing to restore — wrong universe could be wiped."
        )
    if snapshot_data.get("site_domain") != site.domain:
        raise SnapshotSiteMismatch(
            f"Snapshot site_domain={snapshot_data.get('site_domain')!r} "
            f"does not match active site domain={site.domain!r}. "
            "Refusing to restore."
        )


def restore_snapshot(snapshot_path: Path, site) -> None:
    """
    Restore an Object snapshot onto ``site``.

    Re-asserts ``site_pk`` and ``site_domain`` before any write. The
    file's recorded site MUST match the ``site`` argument's actual
    values — otherwise raises ``SnapshotSiteMismatch`` and aborts.

    :param snapshot_path: JSON file written by :func:`capture_snapshot`.
    :param site: Active ``django.contrib.sites.models.Site``.
    """
    from moo.core.models.object import Object
    from moo.core.models.property import Property

    snapshot_data = json.loads(snapshot_path.read_text())
    _assert_site_matches(snapshot_data, site)

    existing = {obj.pk: obj for obj in Object.global_objects.filter(site=site)}
    object_by_pk: dict[int, Any] = dict(existing)

    location_updates: list[Any] = []
    for entry in snapshot_data["objects"]:
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

    for entry in snapshot_data["objects"]:
        obj = existing.get(entry["pk"])
        if obj is None:
            continue
        snapshot_props = entry.get("properties", {})
        live_props = {p.name: p for p in obj.properties.all()}
        for name, raw_value in snapshot_props.items():
            value = _deserialize_value(raw_value, object_by_pk)
            prop = live_props.get(name)
            if prop is None:
                obj.set_property(name, value)
            else:
                if prop.value != value:
                    prop.value = value
                    prop.save(update_fields=["value"])
