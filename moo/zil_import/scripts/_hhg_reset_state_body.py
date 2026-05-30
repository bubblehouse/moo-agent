# Reset HHG world state to canonical opening positions.
#
# HHG's canonical opening (misc.zil:GO at line 179) sets:
#   <SETG WINNER ,PROTAGONIST>
#   <SETG PLAYER ,PROTAGONIST>
#   <SETG HERE ,BEDROOM>
#   <SETG IDENTITY-FLAG ,ARTHUR>
#   <MOVE ,ARTHUR ,GLOBAL-OBJECTS>
#   <SETG LYING-DOWN T>
#   <MOVE ,PROTAGONIST ,BED>
#
# The converter only captures top-level <GLOBAL> / <SETG> forms; the
# initialisation inside GO doesn't flow through, so we seed it here.
# Idempotent.  Hardcodes ``site = 'hhg.local'``.
import datetime as _dt
import json as _json
from pathlib import Path

from django.contrib.sites.models import Site
from moo.core.code import ContextManager
from moo.core.models.acl import Access, _get_permission_id
from moo.core.models.object import Object
from moo.core.models.property import Property

# Snapshot of the post-bootstrap, pre-play world.  First reset captures;
# subsequent resets restore.  Lives under /usr/app/snapshots (mounted
# from ../moo-agent/snapshots in compose.override.yml).  Capture/restore
# helpers are inlined below because ``extras/`` isn't on the in-container
# import path — only ``moo/`` is mounted, so we can't ``from
# moo.zil_import.snapshot import …``.
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
    print(f"hhg reset: captured snapshot to {snapshot_path} ({len(objects_data)} objects)")


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
    print(f"hhg reset: restored snapshot from {snapshot_path}")


def _reset_hhg_world(site):
    """Apply the canonical world-state reset against ``site``."""
    ContextManager.set_site(site)

    # Capture-or-restore snapshot of object positions / properties.
    # First call after sync: file doesn't exist → capture from clean state.
    # Subsequent calls: restore that snapshot → wipes session pollution
    # (gown stuck in Hold, daemon counters past fire points, etc.).
    snapshot_path = _SNAPSHOT_DIR / f"hhg-site-{site.pk}.json"
    try:
        if snapshot_path.exists():
            _snapshot_restore(snapshot_path, site)
        else:
            _snapshot_capture(site, "hhg", snapshot_path)
    except _SnapshotSiteMismatch as exc:
        print(f"hhg reset: snapshot site mismatch, skipping restore: {exc}")
    except Exception as exc:  # pylint: disable=broad-except
        print(f"hhg reset: snapshot {type(exc).__name__}: {exc}")

    # Non-wizard Adventurer is the gameplay avatar (matches Zork's pattern).
    adventurer = Object.global_objects.get(name="Adventurer", site=site)
    bedroom = Object.global_objects.get(name="Bedroom", site=site)
    arthur = Object.global_objects.filter(name="Arthur Dent", site=site).first()

    # Place the player in the bedroom.
    adventurer.location = bedroom
    adventurer.save()

    # Seed IDENTITY-FLAG so identity-keyed verbs dispatch correctly.
    # Zstate property names follow the snake-case convention used by
    # zstate_get('IDENTITY-FLAG') → 'zstate_identity_flag'.
    if arthur is not None:
        adventurer.set_property("zstate_identity_flag", arthur)
    # Canonical opening sets LYING-DOWN=True (player wakes in BED).  We
    # place the player at Bedroom (not BED), so the bed-disembark puzzle
    # is bypassed — keep LYING-DOWN False so the downstream
    # ``block bulldozer`` / ``lie in front of bulldozer`` puzzle isn't
    # short-circuited by GROUND-F's "You already are!" rebuke.
    adventurer.set_property("zstate_lying_down", False)
    # Short-circuit the substrate's lit? check so describe_room doesn't
    # report every room as "pitch black" — mirrors Zork's reset. The
    # substrate reads zstate_lit / zstate_always_lit off the player, and
    # those are unset without an explicit seed.
    adventurer.set_property("zstate_lit", True)
    adventurer.set_property("zstate_always_lit", True)
    # Seed the daemon / queue / counter state the substrate reads each
    # turn. Without these, the first call to zstate_get raises
    # NoSuchPropertyError. Mirrors Zork's reset.
    # The three startup daemons match HHG's GO routine (misc.zil:179):
    #   <ENABLE <QUEUE I-HOUSEWRECK 20>>  ; bulldozer rolls in at turn 20
    #   <ENABLE <QUEUE I-THING 21>>       ; pocket fluff stir-and-roll at 21
    #   <ENABLE <QUEUE I-VOGONS 50>>      ; Vogon fleet arrival at 50, drives
    #                                       Earth→Hold transition (multi-tick)
    # Without these the player never reaches the Vogon Hold scene naturally.
    # Queue-entry shape matches verbs/system/queue.py.
    adventurer.set_property(
        "zstate_queue",
        [
            {"name": "i-housewreck", "fire_at_turn": 20},
            {"name": "i-thing", "fire_at_turn": 21},
            {"name": "i-vogons", "fire_at_turn": 50},
        ],
    )
    adventurer.set_property("zstate_drop", [])
    adventurer.set_property("zstate_moves", 0)
    adventurer.set_property("zstate_deaths", 0)
    adventurer.set_property("zstate_score", 0)
    # Daemon counters — reset every session so a prior-run BULLDOZER /
    # PROSSER / VOGON tick count doesn't carry over and immediately
    # trigger BRICK-DEATH the first time the player reaches Front of
    # House.  The realtime daemon scheduler currently fires every tick
    # without honouring ZIL's queue delays (see references/known-quirks),
    # so these counters race to their death thresholds within a few
    # moves — which means stale state from a prior session = immediate
    # game-over on session start.
    adventurer.set_property("zstate_bulldozer_counter", 0)
    adventurer.set_property("zstate_prosser_counter", 0)
    adventurer.set_property("zstate_vogon_counter", 0)
    adventurer.set_property("zstate_ford_counter", 0)
    adventurer.set_property("zstate_dead_counter", 0)
    adventurer.set_property("zstate_drunk_level", 0)
    adventurer.set_property("zstate_house_demolished", False)
    adventurer.set_property("zstate_prosser_lying", False)
    adventurer.set_property("zstate_towel_offered", False)
    adventurer.set_property("zstate_gone_around", False)
    adventurer.set_property("zstate_ford_gone", False)
    adventurer.set_property("zstate_earth_demolished", False)
    # Dark-dream / improbability-drive state.  The snapshot was captured
    # from a clean world where the Adventurer had never entered the Dark,
    # so it carries NO ``action`` / ``zstate_*_prob`` / ``zstate_dark_*``
    # properties — which means the snapshot restore can never *clear* them
    # once a session sets them.  A session that ends mid-Dark (before
    # LEAVE-DARK resets ``action`` to ``protagonist_f``) leaves the player
    # waking up in the Bedroom with ``action='dark_function'`` intercepting
    # every command, and with the prob globals knocked off their canonical
    # values (e.g. VOGON-PROB 100 → 10 after the first DARK-F roll) so the
    # next hitchhike routes to the wrong dark destination.  Re-seed the
    # GLOBAL defaults (globals.zil) and the canonical player ACTION
    # (globals.zil:1085 PUTP PROTAGONIST P?ACTION PROTAGONIST-F) here so a
    # fresh reset always starts outside the dream with the Vogon Hold as
    # the first improbability destination.
    adventurer.set_property("action", "protagonist_f")
    adventurer.set_property("zstate_heart_prob", 0)
    adventurer.set_property("zstate_vogon_prob", 100)
    adventurer.set_property("zstate_traal_prob", 60)
    adventurer.set_property("zstate_fleet_prob", 0)
    adventurer.set_property("zstate_whale_prob", 0)
    adventurer.set_property("zstate_trillian_prob", 15)
    adventurer.set_property("zstate_ford_prob", 15)
    adventurer.set_property("zstate_zaphod_prob", 0)
    adventurer.set_property("zstate_dark_controlled", False)
    adventurer.set_property("zstate_dark_counter", 0)
    adventurer.set_property("zstate_dark_flag", False)
    adventurer.set_property("zstate_dreaming", False)
    adventurer.set_property("zstate_current_exit", 0)
    adventurer.set_property("zstate_lying_counter", 0)
    adventurer.set_property("zstate_tea_counter", 0)
    # Babel-fish puzzle (Vogon Hold) globals — same snapshot gap: these
    # zstate values aren't in the captured (pre-Hold) snapshot, so a
    # session that played the puzzle leaves FISH-COUNTER=0 (dispenser
    # empty → "Click"), GOWN-HUNG / PANEL-BLOCKER / ITEM-ON-SATCHEL stuck,
    # and the next natural arrival can't solve it.  Re-seed the GLOBAL
    # defaults (vogon.zil:134-140) so the dispenser is loaded and the
    # puzzle starts unsolved.
    adventurer.set_property("zstate_fish_counter", 5)
    adventurer.set_property("zstate_gown_hung", False)
    adventurer.set_property("zstate_panel_blocker", False)
    adventurer.set_property("zstate_item_on_satchel", False)
    # FORD-SLEEPING gates the I-FORD "nap" in the Vogon Hold that drops
    # Ford's satchel into the room (earth.zil:1221 MOVE SATCHEL HERE) so
    # the player can take it for the babel-fish panel-blocking step.  Left
    # True (snapshot gap), the nap never re-fires and the satchel stays
    # stuck inside off-stage Ford — unreachable at the Hold.  Clear it so
    # the daemon re-arms.  (NOTE: a fully clean re-arm also needs the
    # satchel/towel/Ford object positions restored — tracked in BUGS.md;
    # this clear is the per-turn flag half of that fix.)
    adventurer.set_property("zstate_ford_sleeping", False)
    adventurer.save()

    # Seed player_start on the System Object so V-JIGS-UP can teleport
    # back after a lethal hit instead of erroring with "no player_start
    # property defined". Bedroom matches the canonical opening location.
    system_object = Object.global_objects.get(name="System Object", site=site)
    system_object.set_property("player_start", bedroom)
    system_object.save()

    # Restore canonical object flags the snapshot doesn't reset.  The
    # THUMB (electronic Sub-Etha signaling device) starts un-munged in
    # ZIL (FLAGS TAKEBIT VOWELBIT CONTBIT OPENBIT — no MUNGEDBIT).  But a
    # mis-timed ``push green button`` (fleet absent / pushed after death)
    # routes through GREEN-BUTTON-F's catch-all branch which sets
    # MUNGEDBIT, and once it's stuck the Earth→Vogon-Hold hitchhike fails
    # with "feeble clicking noises" on every subsequent run because the
    # snapshot captured the broken flag.  Clear it on reset so the
    # canonical "push green button to hitchhike" puzzle is solvable from
    # a clean session.
    thumb = Object.global_objects.filter(name="electronic Sub-Etha signaling device", site=site).first()
    if thumb is not None and thumb.flag("mungedbit"):
        thumb.set_flag("mungedbit", False)

    # Clear ``touchbit`` / ``revisitbit`` / ``ndescbit`` on every room so a
    # fresh run starts fully un-visited (mirrors zork1's reset sweep).
    # ``touchbit`` means "the player has seen this room this session";
    # ``revisitbit`` marks dream-sequence re-entry; ``ndescbit`` is the
    # "M-END first-visit setup already ran" sentinel that room enterfuncs
    # set after firing.  None of these is in the captured snapshot (the
    # snapshot was taken from a clean world where no room had been entered),
    # so the snapshot restore can never *clear* them once a session sets them.
    #
    # Two concrete failures this fixes:
    #  - COUNTRY-LANE-F's M-ENTER tests ``<FSET? ,HOLD ,TOUCHBIT>`` — once a
    #    prior session reaches the Vogon Hold, ``hold.touchbit`` sticks True
    #    forever, so re-entering the Country Lane fires the "second time
    #    around" branch that flips IDENTITY-FLAG to FORD.  As Ford, PUB-F
    #    enables I-UNEASY (the "Do as you would have done by" universe-ends
    #    death) and refuses to let Ford buy beer — wedging the natural
    #    Earth-escape on every reset.  COUNTRY-LANE-F's M-END also reads
    #    ``revisitbit`` for a JIGS-UP, so clear that too.
    #  - HOLD-F's M-END (vogon.zil) is gated on ``<NOT <FSET? ,HOLD ,NDESCBIT>>``
    #    and sets ``ndescbit`` after queuing I-FORD/I-GROGGY/I-GUARDS.  Once a
    #    prior session enters the Hold, ``hold.ndescbit`` sticks True, the M-END
    #    never re-fires, I-FORD is never queued, and the babel-fish puzzle's
    #    satchel-drop (I-FORD's <MOVE ,SATCHEL ,HERE> after 6 turns) never
    #    happens — ``take satchel`` fails on every subsequent run.  No HHG room
    #    canonically starts with NDESCBIT (verified against the ZIL room FLAGS),
    #    so clearing it restores the canonical first-visit state for all rooms.
    room_cls = Object.global_objects.filter(name="Room", site=site).first()
    if room_cls is not None:
        for _room in room_cls.children.all():
            _room.set_property("touchbit", False)
            _room.set_property("revisitbit", False)
            _room.set_property("ndescbit", False)

    # Property-level write grants on every substrate-classed instance so
    # Adventurer can mutate world state at runtime.  Mirrors Zork's reset.
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

    print("hhg reset")


_site = Site.objects.filter(domain="hhg.local").first()
if _site is None:
    print("hhg reset: site not yet created, skipping")
else:
    _reset_hhg_world(_site)
