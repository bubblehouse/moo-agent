# Reset Zork 1 world state to canonical opening positions.
#
# Two callers:
#   1. moo_init --bootstrap zork1 [--sync] — generator.py copies this file
#      to moo/bootstrap/zork1/099_reset_state.py so it runs after rooms /
#      objects / exits are loaded, putting the world at a known starting
#      state on every (re)bootstrap.
#   2. moo/zil_import/scripts/zork1_smoke.py — reads this file's text
#      and passes it to `manage.py shell -c` before the smoke walks the
#      canonical opening, so smoke runs are idempotent regardless of how
#      the previous run ended.
#
# Idempotent.  Hardcodes ``site = 'zork1.local'`` because the zork1
# bootstrap currently maps to that domain only.
import datetime as _dt
import json as _json
from pathlib import Path

from django.contrib.sites.models import Site
from moo.core.code import ContextManager
from moo.core.models.acl import Access, _get_permission_id
from moo.core.models.auth import Player
from moo.core.models.object import Object
from moo.core.models.property import Property

# Snapshot of the post-bootstrap, pre-play world.  Helpers inlined
# below — ``extras/`` isn't on the in-container import path so we can't
# ``from moo.zil_import.snapshot import …``.
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
    print(f"zork1 reset: captured snapshot to {snapshot_path} ({len(objects_data)} objects)")


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
    print(f"zork1 reset: restored snapshot from {snapshot_path}")


def _reset_zork1_world(site):
    """Apply the canonical world-state reset against ``site``.

    Wrapped in a function so this file is safe to ``exec`` during the
    bootstrap pass too: when test fixtures or first-time ``moo_init``
    don't yet have a ``zork1.local`` Site row, the dispatch below skips
    this call entirely.
    """
    # Every Object.save() below dispatches the 'accept' verb on the new
    # location, and verb dispatch needs the active site set on the
    # ContextManager (lookup("System Object") fails otherwise).  moo_init
    # sets this before calling the bootstrap; the smoke and any direct
    # `manage.py shell -c` invocation does not — so set it idempotently.
    ContextManager.set_site(site)

    # Capture-or-restore snapshot of object positions / properties.
    # First call after a fresh sync: file doesn't exist → capture from
    # the clean state.  Subsequent calls: restore that snapshot →
    # wipes session pollution (treasures missing from canonical spots,
    # daemon counters mid-cycle, etc.) before per-session seeding below.
    snapshot_path = _SNAPSHOT_DIR / f"zork1-site-{site.pk}.json"
    try:
        if snapshot_path.exists():
            _snapshot_restore(snapshot_path, site)
        else:
            _snapshot_capture(site, "zork1", snapshot_path)
    except _SnapshotSiteMismatch as exc:
        print(f"zork1 reset: snapshot site mismatch, skipping restore: {exc}")
    except Exception as exc:  # pylint: disable=broad-except
        print(f"zork1 reset: snapshot {type(exc).__name__}: {exc}")

    # Was: Object.global_objects.get(name="Wizard") — the Wizard avatar still
    # exists and owns every world object, but gameplay now runs through the
    # non-wizard Adventurer avatar so smoke + zork_session exercise real
    # ACL enforcement (the wizards group bypass made permission bugs invisible).
    wiz = Object.global_objects.get(name="Adventurer", site=site)
    woh = Object.global_objects.get(name="West of House", site=site)
    mailbox = Object.global_objects.get(name="small mailbox", site=site)
    leaflet = Object.global_objects.get(name="leaflet", site=site)
    attic = Object.global_objects.get(name="Attic", site=site)
    lr = Object.global_objects.get(name="Living Room", site=site)
    rope = Object.global_objects.get(name="rope", site=site)
    sword = Object.global_objects.get(name="sword", site=site)
    lantern = Object.global_objects.get(name="brass lantern", site=site)
    trap = Object.global_objects.get(name="trap door", site=site)
    nest = Object.global_objects.get(name="bird's nest", site=site)
    egg = Object.global_objects.get(name="jewel-encrusted egg", site=site)
    gallery = Object.global_objects.get(name="Gallery", site=site)
    painting = Object.global_objects.get(name="painting", site=site)
    torch = Object.global_objects.get(name="torch", site=site)
    pedestal = Object.global_objects.get(name="pedestal", site=site)
    north_temple = Object.global_objects.get(name="Temple", site=site)
    bell = Object.global_objects.get(name="brass bell", site=site)
    altar = Object.global_objects.get(name="altar (ALTAR)", site=site)
    book = Object.global_objects.get(name="black book", site=site)
    candles = Object.global_objects.get(name="pair of candles", site=site)
    egypt = Object.global_objects.get(name="Egyptian Room", site=site)
    coffin = Object.global_objects.get(name="gold coffin", site=site)
    case = Object.global_objects.get(name="trophy case", site=site)
    treasure_room = Object.global_objects.get(name="Treasure Room", site=site)
    chalice = Object.global_objects.get(name="chalice", site=site)
    leaflet.location = mailbox
    leaflet.save()
    rope.location = attic
    rope.save()
    sword.location = lr
    sword.save()
    lantern.location = lr
    lantern.save()
    # Reset the broken-lantern back to limbo.  V-THROW on the brass lantern
    # moves the broken_lamp into the player's room, and the canonical reset
    # doesn't restore it — leaving "broken lantern" lingering in Living
    # Room across sessions and creating a permanent ambiguity with the
    # brass lantern any time the smoke tries ``take lantern``.
    broken_lamp = Object.global_objects.filter(name="broken lantern", site=site).first()
    if broken_lamp:
        broken_lamp.location = None
        broken_lamp.save()
    egg.location = nest
    egg.save()
    # Re-park the bird's nest itself to Up a Tree (its canonical home).
    # The reset nests the egg inside it but never restored the nest's
    # own location, so a prior session that carried the nest down left
    # it — and the egg + canary riding inside — stranded in the avatar's
    # inventory across runs.
    up_a_tree = Object.global_objects.get(name="Up a Tree", site=site)
    nest.location = up_a_tree
    nest.save()
    painting.location = gallery
    painting.save()
    torch.location = pedestal
    torch.save()
    bell.location = north_temple
    bell.save()
    book.location = altar
    book.save()
    candles.location = altar
    candles.save()
    # LLD ritual state: bell becomes hot-bell after ringing, candles
    # get burned, and LLD-FLAG / XB / XC track the ceremony progress.
    # Reset all of it so re-runs see a fresh ritual.
    # MATCH-COUNT (canonical 6) is decremented every light-match; stale runs
    # leave it at 0 ("I'm afraid that you have run out of matches"), breaking
    # the LLD ritual on repeat runs.  Reset to 6 here so each smoke run can
    # burn 6 matches before depletion.
    wiz.set_property("zstate_match_count", 6)
    matchbook = Object.global_objects.get(name="matchbook", site=site)
    dam_lobby = Object.global_objects.get(name="Dam Lobby", site=site)
    matchbook.location = dam_lobby
    matchbook.save()
    matchbook.set_property("onbit", False)
    matchbook.set_property("flamebit", False)
    matchbook.save()
    # Guidebook: canonical Dam Lobby occupant.  Bootstrap places it here,
    # but the thief's STEAL-JUNK will grab it (junk = tvalue=0) on any run
    # that exercises the outdoor-walk cycle.  Without re-placement the next
    # run finds an empty Dam Lobby.
    guidebook = Object.global_objects.filter(name="tour guidebook", site=site).first()
    if guidebook:
        guidebook.location = dam_lobby
        guidebook.save()
    candles.set_property("onbit", False)
    candles.set_property("touchbit", False)
    candles.set_property("rmungbit", False)
    candles.save()
    bell.set_property("touchbit", False)
    bell.save()
    hot_bell = Object.global_objects.filter(name="hot bell", site=site).first()
    if hot_bell:
        hot_bell.location = None
        hot_bell.save()
    skull = Object.global_objects.get(name="crystal skull", site=site)
    lld_room = Object.global_objects.filter(name="Land of the Dead", site=site).first()
    if skull and lld_room:
        skull.location = lld_room
        skull.save()
    wiz.set_property("zstate_lld_flag", False)
    wiz.set_property("zstate_xb", False)
    wiz.set_property("zstate_xc", False)
    # Bauble: not in the world initially — appears when canary is wound in a
    # forest room.  Reset SING-SONG flag and remove any bauble stranded from
    # previous runs so the wind summons a fresh one.
    wiz.set_property("zstate_sing_song", False)
    bauble = Object.global_objects.filter(name="beautiful brass bauble", site=site).first()
    if bauble:
        bauble.location = None
        bauble.save()
    coffin.location = egypt
    coffin.save()
    canary = Object.global_objects.get(name="golden clockwork canary", site=site)
    sceptre = Object.global_objects.get(name="sceptre", site=site)
    broken_egg_obj = Object.global_objects.get(name="broken jewel-encrusted egg", site=site)
    broken_canary_obj = Object.global_objects.get(name="broken clockwork canary", site=site)
    canary.location = egg
    canary.save()
    sceptre.location = coffin
    sceptre.save()
    broken_egg_obj.location = None
    broken_egg_obj.save()
    broken_canary_obj.location = broken_egg_obj
    broken_canary_obj.save()
    # Pre-open the egg so the unbroken canary is accessible without going
    # through V-MUNG (which always triggers BAD-EGG and replaces canary
    # with broken_canary, breaking the bauble path).  In canonical Zork
    # only the thief opens the egg cleanly; we shortcut by setting OPENBIT
    # at bootstrap time so the smoke can wind the canary in a forest room.
    egg.set_property("open", True)
    egg.save()
    # Clear ``invisible`` on every treasure the thief might have grabbed
    # in a prior session.  ROB() sets ``invisible=True`` when items move
    # into the thief's bag, and the reset moves them back to canonical
    # locations but doesn't clear the flag — leaving the items hidden
    # from PRINT-CONT (so ``inventory`` and ``look`` would skip them
    # entirely on subsequent runs).
    for _treasure_name in (
        "jewel-encrusted egg",
        "golden clockwork canary",
        "sceptre",
        "broken jewel-encrusted egg",
        "broken clockwork canary",
        "small mailbox",
        "leaflet",
        "rope",
        "sword",
        "brass lantern",
        "torch",
        "painting",
        "trophy case",
        "pair of candles",
        "black book",
        "brass bell",
        "gold coffin",
        "chalice",
        "huge diamond",
        "large emerald",
        "platinum bar",
        "sapphire-encrusted bracelet",
        "beautiful jeweled scarab",
        "beautiful brass bauble",
        "crystal skull",
        "crystal trident",
        "jade figurine",
        "leather bag of coins",
        "pot of gold",
        "trunk of jewels",
        "ancient map",
    ):
        _t = Object.global_objects.filter(name=_treasure_name, site=site).first()
        if _t is not None:
            _t.set_property("invisible", False)
            _t.obvious = True
            _t.save()
    # Also clear ``invisible`` on the non-treasure utility items the thief
    # bags (STEAL-JUNK doesn't filter to treasures only).  When the reset
    # below moves these back to their canonical rooms, the invisible flag
    # from a prior session would otherwise leave them un-takeable.
    for _junk_name in (
        "matchbook",
        "wrench",
        "screwdriver",
        "tour guidebook",
    ):
        _j = Object.global_objects.filter(name=_junk_name, site=site).first()
        if _j is not None:
            _j.set_property("invisible", False)
            _j.obvious = True
            _j.save()
    coffin.set_property("open", False)
    coffin.save()
    chalice.location = treasure_room
    chalice.save()
    mailbox.set_property("open", False)
    mailbox.save()
    trap.set_property("open", False)
    trap.save()
    case.set_property("open", False)
    case.save()
    # Shaft basket: canonical opening has RAISED-BASKET in SHAFT-ROOM and
    # LOWERED-BASKET in LOWER-SHAFT (= "Drafty Room") with CAGE-TOP=True.
    # ZIL's BASKET-F lower/raise verbs swap the two between rooms, so a
    # previous run that lowered the basket leaves LOWERED-BASKET stuck in
    # SHAFT-ROOM and the substrate ``put.py`` rejects "put coal in basket"
    # because LOWERED-BASKET has no OPEN/OPENABLE/VEHICLE flag.
    raised_basket = Object.global_objects.filter(name="basket (RAISED-BASKET)", site=site).first()
    lowered_basket = Object.global_objects.filter(name="basket (LOWERED-BASKET)", site=site).first()
    shaft_room = Object.global_objects.filter(name="Shaft Room", site=site).first()
    lower_shaft = Object.global_objects.filter(name="Drafty Room", site=site).first()
    if raised_basket and shaft_room:
        raised_basket.location = shaft_room
        raised_basket.save()
    if lowered_basket and lower_shaft:
        lowered_basket.location = lower_shaft
        lowered_basket.save()
    wiz.set_property("zstate_cage_top", True)
    wiz.set_property("zstate_rug_moved", False)
    wiz.set_property("zstate_score", 0)
    wiz.set_property("zstate_base_score", 0)
    # WON-FLAG gates the SW path from West-of-House to Stone Barrow (the Zork
    # endgame portal).  When ``finish.py`` crashed mid-victory the flag stuck
    # True on the avatar, leaving the trap open in subsequent sessions.
    # Always reset to False so a fresh agent starts at the canonical opening
    # and the conditional exits stay closed until the game is actually won.
    wiz.set_property("zstate_won_flag", False)
    # Simulate the post-cyclops state: ULYSSES has already been said.
    # Without this, Living Room west ("The door is nailed shut.") and
    # Cyclops Room up ("The cyclops doesn't look like he'll let you past.")
    # are both blocked, cascading into chalice / diamond / bracelet / bar /
    # scarab unreachable.  The smoke doesn't drive the maze path needed to
    # reach Cyclops Room before MAGIC-FLAG is set, so seed both flags here.
    # When the smoke gains a real maze traversal, this seed can be dropped
    # in favour of running the cyclops scene end-to-end.
    wiz.set_property("zstate_magic_flag", True)
    wiz.set_property("zstate_cyclops_flag", True)
    # Restore first-visit room VALUE bonuses — SCORE-OBJ zeroes ``value`` after
    # crediting it, so a previous smoke run will have left these at 0.  Re-seed
    # from the canonical ZIL values so each smoke run accumulates the full
    # room-discovery bonus (Kitchen=10, Cellar=25, Treasure-Room=25,
    # EW-Passage=5 = 65 total).
    for _name, _val in (("Kitchen", 10), ("Cellar", 25), ("Treasure Room", 25), ("East-West Passage", 5)):
        _r = Object.global_objects.filter(name=_name, site=site).first()
        if _r:
            _r.set_property("value", _val)
    # LIGHT-SHAFT: reset to 13 so the timber-room bonus fires each run.
    wiz.set_property("zstate_light_shaft", 13)
    # Restore per-treasure first-take VALUE — same reset reason as room values.
    for _treasure_atom in (
        "crystal skull",
        "sceptre",
        "chalice",
        "crystal trident",
        "gold coffin",
        "huge diamond",
        "jade figurine",
        "leather bag of coins",
        "large emerald",
        "painting",
        "platinum bar",
        "pot of gold",
        "sapphire-encrusted bracelet",
        "beautiful jeweled scarab",
        "torch",
        "trunk of jewels",
        "jewel-encrusted egg",
        "beautiful brass bauble",
        "golden clockwork canary",
    ):
        _t = Object.global_objects.filter(name=_treasure_atom, site=site).first()
        if _t and _t.has_property("tvalue"):
            # canonical (V, T) per ZIL — picked up from moo/zil_import IR.
            _v_map = {
                "crystal skull": 10,
                "sceptre": 4,
                "chalice": 10,
                "crystal trident": 4,
                "gold coffin": 10,
                "huge diamond": 10,
                "jade figurine": 5,
                "leather bag of coins": 10,
                "large emerald": 5,
                "painting": 4,
                "platinum bar": 10,
                "pot of gold": 10,
                "sapphire-encrusted bracelet": 5,
                "beautiful jeweled scarab": 5,
                "torch": 14,
                "trunk of jewels": 15,
                "jewel-encrusted egg": 5,
                "beautiful brass bauble": 1,
                "golden clockwork canary": 6,
            }
            _t.set_property("value", _v_map[_treasure_atom])
    wiz.set_property("zstate_dome_flag", False)
    wiz.set_property("zstate_lit", True)
    # Clear daemon queue + turn counter + GO-ran flag + drop-list so a
    # previous run's stale state doesn't carry over.  The canonical
    # at-start daemons are now queued by GO itself on the player's first
    # command of the next session (see do_command.py ``zstate_started``
    # hook).  The ZIL routines that GO calls are:
    #
    # - i-forest-room: queued by each forest_*/enterfunc.py via
    #   ``_.schedule_realtime("i_forest_room", -1)`` (realtime mode).
    # - i-thief: queued by GO via ``_.schedule_realtime("i_thief", -1)``.
    # - i-bat: queued by bat_room/enterfunc.py on entry.
    # - i-fight / i-sword: queued by GO into the turn queue.
    # - i-candles / i-lantern: queued by GO with positive delay.
    # - i-river / i-rfill / i-rempty: self-queued by goto on water rooms.
    # - i-cyclops: queued by combat dispatch.
    wiz.set_property("zstate_queue", [])
    wiz.set_property("zstate_drop", [])
    wiz.set_property("zstate_moves", 0)
    wiz.set_property("zstate_started", False)
    # DEATHS is incremented by verbs/system/death.py on every lethal hit
    # and read back by V-DIAGNOSE.  Nothing else cleared it, so a fresh
    # session reported "You have been killed twice." carried over from
    # prior runs.  Reset to 0 so diagnose starts clean.
    wiz.set_property("zstate_deaths", 0)
    # Short-circuit lit? — the ZIL lit? routine walks parser-internal tables
    # (P-MERGE / P-SLOCBITS / DO-SL) that we don't initialise, so calls to
    # lit? from goto() crash on uninitialised state.  ALWAYS-LIT is read
    # first in lit? and returns True without touching the parser tables.
    wiz.set_property("zstate_always_lit", True)
    wiz.location = woh
    wiz.save()
    # Death (V-JIGS-UP / verbs/system/death.py) reads ``player_start`` off
    # the System Object to teleport the player back after a lethal hit.
    # Without it, every death prints "There is no 'player_start' property
    # defined." and the player is stranded with stale flags.  Seed it to
    # West-of-House to match canonical Zork.
    system_object = Object.global_objects.get(name="System Object", site=site)
    system_object.set_property("player_start", woh)
    system_object.save()
    # Relocate kitchen-window from LOCAL-GLOBALS to East-of-House so the
    # parser's local-scope name search ("examine window", "open window")
    # resolves it.  The canonical ZIL pattern was multi-room global scenery,
    # but DjangoMOO's parser only searches the player's room's contents,
    # so single-location placement at the room you interact with from is
    # the working compromise.  Trade-off: from inside the kitchen, the
    # window is no longer reachable by name — acceptable, since the
    # canonical interaction (open window, go in) happens from outside.
    kitchen_window = Object.global_objects.get(name="kitchen window", site=site)
    east_of_house = Object.global_objects.get(name="Behind House", site=site)
    kitchen_window.location = east_of_house
    kitchen_window.set_property("open", False)
    kitchen_window.save()
    # Same global_scenery → single-location patch for the forest tree.
    # Forest Path is where canonical Zork stages the climb-the-tree puzzle
    # (up reaches Up-A-Tree with the bird's-nest), so that's the room where
    # ``examine tree`` / ``climb tree`` need the tree to resolve.  Forest 1/2/3
    # still describe trees in flavor text but don't expose an interactable.
    forest_tree = Object.global_objects.filter(name="tree", site=site).first()
    forest_path_room = Object.global_objects.filter(name="Forest Path", site=site).first()
    if forest_tree and forest_path_room:
        forest_tree.location = forest_path_room
        forest_tree.save()
    # Also park every player on the zork1 site at West-of-House and clear
    # their WON-FLAG so a fresh session (or an agent restart after a
    # get-stuck-at-Stone-Barrow run) always lands at the canonical opening
    # with the SW endgame portal closed.
    # Was filtered by parents__name="Player", which caught Wizard (direct
    # parent Player) but NOT Adventurer (direct parent is Zork Player).
    # Iterating Player records on the site is what we semantically want
    # anyway — every connected avatar resets to canonical opening state.
    for _player_record in Player.objects.filter(site=site, avatar__isnull=False):  # pylint: disable=no-member
        _avatar = _player_record.avatar
        _avatar.location = woh
        _avatar.set_property("zstate_won_flag", False)
        _avatar.save()
    kitchen_table = Object.global_objects.get(name="kitchen table", site=site)
    sandwich_bag = Object.global_objects.get(name="brown sack", site=site)
    garlic = Object.global_objects.get(name="clove of garlic", site=site)
    lunch = Object.global_objects.get(name="lunch", site=site)
    jade = Object.global_objects.get(name="jade figurine", site=site)
    platinum_bar = Object.global_objects.get(name="platinum bar", site=site)
    loud_room = Object.global_objects.get(name="Loud Room", site=site)
    diamond = Object.global_objects.get(name="huge diamond", site=site)
    coal = Object.global_objects.get(name="small pile of coal", site=site)
    screwdriver = Object.global_objects.get(name="screwdriver", site=site)
    bracelet = Object.global_objects.get(name="sapphire-encrusted bracelet", site=site)
    bat_room = Object.global_objects.get(name="Bat Room", site=site)
    gas_room = Object.global_objects.get(name="Gas Room", site=site)
    dead_end_5 = Object.global_objects.get(name="Dead End (DEAD-END-5)", site=site)
    maintenance_room = Object.global_objects.get(name="Maintenance Room", site=site)
    machine = Object.global_objects.get(name="machine", site=site)
    sandwich_bag.location = kitchen_table
    sandwich_bag.save()
    # Canonical: garlic lives inside the brown sack (which starts open).
    # The kitchen floor placement was a smoke shortcut that broke the
    # canonical "open sack and take garlic" presentation.  Re-park it
    # inside; ``take garlic`` still works because the parser finds the
    # item by alias through an open container.
    garlic.location = sandwich_bag
    garlic.save()
    lunch.location = sandwich_bag
    lunch.save()
    jade.location = bat_room
    jade.save()
    platinum_bar.location = loud_room
    platinum_bar.save()
    diamond.location = None
    diamond.save()
    coal.location = dead_end_5
    coal.save()
    screwdriver.location = maintenance_room
    screwdriver.save()
    bracelet.location = gas_room
    bracelet.save()
    # Reset WATER-LEVEL so the i-maint-room daemon doesn't try to index
    # past the DROWNINGS table (9 entries) on the first tick of a new
    # session.  Stale runs accumulate WATER-LEVEL because MUNG-ROOM only
    # jigs the player if they're inside — leaving the daemon scheduled
    # with a continuously incrementing level when the player escaped.
    wiz.set_property("zstate_water_level", 0)
    # Reset LOUD-FLAG so the Loud Room puzzle starts fresh: the canonical
    # noisy-room state where `take bar` fails until the player types
    # `echo`.  Stale runs leave LOUD-FLAG=True ("eerie in its quietness")
    # and the bar take freebie's an unjustified +10 points.  Also reset
    # the bar's sacred flag — echo permanently clears it; without resetting
    # the bar stays takeable without echo on the next run.
    wiz.set_property("zstate_loud_flag", False)
    platinum_bar_obj = Object.global_objects.filter(name="platinum bar", site=site).first()
    if platinum_bar_obj:
        platinum_bar_obj.set_property("sacred", True)
        platinum_bar_obj.save()
    machine.set_property("open", False)
    # Clear machine contents so coal→diamond puzzle starts clean
    gunk = Object.global_objects.filter(name="small piece of vitreous slag", site=site).first()
    if gunk and gunk.location == machine:
        gunk.location = None
        gunk.save()
    diamond_obj = Object.global_objects.filter(name="huge diamond", site=site).first()
    if diamond_obj and diamond_obj.location == machine:
        diamond_obj.location = None
        diamond_obj.save()
    mirror_room_1 = Object.global_objects.get(name="Mirror Room (MIRROR-ROOM-1)", site=site)
    mirror_room_2 = Object.global_objects.get(name="Mirror Room (MIRROR-ROOM-2)", site=site)
    # There are two mirror objects (MIRROR-1 in MR1, MIRROR-2 in MR2).  Each
    # rub swaps contents of both rooms so over a run they migrate; reset
    # both back by alias so a second rub during the bar-recovery detour finds
    # a mirror in MR2.
    mirror_1 = Object.global_objects.filter(site=site, aliases__alias="mirror_1").first()
    mirror_2 = Object.global_objects.filter(site=site, aliases__alias="mirror_2").first()
    if mirror_1:
        mirror_1.location = mirror_room_1
        mirror_1.save()
    if mirror_2:
        mirror_2.location = mirror_room_2
        mirror_2.save()
    wiz.set_property("zstate_mirror_mung", False)
    # Boat puzzle (Step 2.4): pre-place the inflated boat at Dam Base so the
    # launch sequence enters the river system (DAM-BASE → RIVER-1 via the
    # RIVER-LAUNCH table).  Reservoir-South would only put the boat on the
    # lake — i-river daemon cancels itself outside RIVER-1..5.
    inflated_boat = Object.global_objects.get(name="magic boat", site=site)
    inflatable_boat = Object.global_objects.filter(name="pile of plastic", site=site).all()
    dam_base = Object.global_objects.get(name="Dam Base", site=site)
    # Reset all boat states first so a previous puncture doesn't accumulate.
    for plastic in inflatable_boat:
        plastic.location = None
        plastic.save()
    inflated_boat.location = dam_base
    inflated_boat.save()
    buoy = Object.global_objects.get(name="red buoy", site=site)
    emerald = Object.global_objects.get(name="large emerald", site=site)
    sandy_beach = Object.global_objects.get(name="Sandy Beach", site=site)
    shovel_obj = Object.global_objects.filter(name="shovel", site=site).first()
    buoy.location = sandy_beach
    buoy.save()
    emerald.location = buoy
    emerald.save()
    buoy.set_property("open", False)
    buoy.save()
    # Reset shovel to SANDY-BEACH (bootstrap default) so multiple smoke
    # runs don't cumulatively drag it into player inventory.
    if shovel_obj:
        shovel_obj.location = sandy_beach
        shovel_obj.save()
    # Reset SCARAB visibility and BEACH-DIG counter so the dig puzzle
    # starts fresh: scarab.invisible=True, BEACH-DIG=0 (incrementing
    # from None would TypeError on first ``dig sand with shovel``).
    scarab = Object.global_objects.filter(name="beautiful jeweled scarab", site=site).first()
    sandy_cave = Object.global_objects.get(name="Sandy Cave", site=site)
    if scarab:
        scarab.location = sandy_cave
        scarab.set_property("invisible", True)
        # Same pattern as pot-of-gold: dig-sand sets obvious=True via set_flag's
        # intrinsic mapping; reset here so the dig puzzle re-arms cleanly.
        scarab.obvious = False
        scarab.save()
    wiz.set_property("zstate_beach_dig", 0)
    # Reset pot-of-gold + rainbow state so the wave-sceptre puzzle starts
    # fresh each smoke run (idempotent).
    pot_of_gold = Object.global_objects.filter(name="pot of gold", site=site).first()
    end_of_rainbow = Object.global_objects.get(name="End of Rainbow", site=site)
    if pot_of_gold:
        pot_of_gold.location = end_of_rainbow
        pot_of_gold.set_property("invisible", True)
        # Wave-sceptre flips Object.obvious to True (via set_flag's intrinsic
        # mapping); reset it here so the puzzle re-arms cleanly.  Without
        # this, the parser would still see the pot at End of Rainbow on a
        # fresh run and ``take pot`` would succeed pre-rainbow.
        pot_of_gold.obvious = False
        pot_of_gold.save()
    wiz.set_property("zstate_rainbow_flag", False)
    # Reset trident to Atlantis Room (sharp object — punctures boat if
    # carried into the boat puzzle, and accumulates in inventory across
    # runs otherwise).
    trident = Object.global_objects.filter(name="crystal trident", site=site).first()
    atlantis_room = Object.global_objects.get(name="Atlantis Room", site=site)
    if trident:
        trident.location = atlantis_room
        trident.save()
    # Reset bag of coins to MAZE-5 so the maze treasure pickup is idempotent.
    bag_of_coins = Object.global_objects.filter(name="leather bag of coins", site=site).first()
    maze_5 = Object.global_objects.get(name="Maze (MAZE-5)", site=site)
    if bag_of_coins:
        bag_of_coins.location = maze_5
        bag_of_coins.save()
    # Reset trunk to RESERVOIR (invisible until i-rempty drains it).  Also
    # reset GATE-FLAG and GATES-OPEN so the bolt sequence is idempotent.
    trunk = Object.global_objects.filter(name="trunk of jewels", site=site).first()
    reservoir = Object.global_objects.get(name="Reservoir", site=site)
    if trunk:
        trunk.location = reservoir
        trunk.set_property("invisible", True)
        # i-rempty's drain flips obvious=True via set_flag; reset.
        trunk.obvious = False
        trunk.save()
    # Reset wrench to MAINTENANCE-ROOM so it's available each run.
    wrench = Object.global_objects.filter(name="wrench", site=site).first()
    if wrench:
        wrench.location = maintenance_room
        wrench.save()
    # Reset tube + ZORK owner's manual to their canonical rooms.  The
    # thief's STEAL-JUNK bags both (tvalue=0), and the thief-emptying
    # sweep further down would otherwise strand them in limbo.
    tube = Object.global_objects.filter(name="tube", site=site).first()
    if tube:
        tube.location = maintenance_room
        tube.save()
    owners_manual = Object.global_objects.filter(name="ZORK owner's manual", site=site).first()
    studio = Object.global_objects.filter(name="Studio", site=site).first()
    if owners_manual and studio:
        owners_manual.location = studio
        owners_manual.save()
    # Reset broken timber to TIMBER-ROOM — it's canonical scenery there
    # but the basket-and-rope detour ``take all`` picks it up.  Without
    # this sweep it accumulates in the wizard's inventory across runs
    # and (at size 50) shoves every subsequent ``take`` over LOAD-ALLOWED.
    broken_timber = Object.global_objects.filter(name="broken timber", site=site).first()
    timber_room = Object.global_objects.filter(name="Timber Room", site=site).first()
    if broken_timber and timber_room:
        broken_timber.location = timber_room
        broken_timber.save()
    wiz.set_property("zstate_gate_flag", None)
    wiz.set_property("zstate_gates_open", None)
    wiz.set_property("zstate_low_tide", None)
    # Reset reservoir flag too (i-rempty sets nonlandbit=False, outdoor=True;
    # revert so the puzzle starts fresh).
    reservoir.set_property("nonlandbit", True)
    reservoir.set_property("outdoor", False)
    reservoir.save()
    # Fix exits whose dest was wrong at initial bootstrap time
    mine_in_exit = Object.global_objects.get(name="in from MINE-ENTRANCE", site=site)
    squeeky_room = Object.global_objects.get(name="Squeaky Room", site=site)
    mine_in_exit.set_property("dest", squeeky_room)
    mine_west_exit = Object.global_objects.get(name="west from MINE-ENTRANCE", site=site)
    mine_west_exit.set_property("dest", squeeky_room)
    # Forest rooms with no climbable tree (Forest-1, Forest-2, Forest-3,
    # Clearing) have their UP-exit nogo_msg set to "There is no tree here
    # suitable for climbing." by the bootstrap.  That message is right
    # for ``climb tree`` (handled by the climb dispatcher's in-scope
    # check) but wrong for a bare ``up`` (player typed the direction, not
    # the climb verb).  Replace with the canonical generic message.
    for _exit_name in (
        "up from FOREST-1",
        "up from FOREST-2",
        "up from FOREST-3",
        "up from CLEARING",
    ):
        _ex = Object.global_objects.filter(name=_exit_name, site=site).first()
        if _ex:
            _ex.set_property("nogo_msg", "You can't go that way.")
    # Villain restoration — combat's <REMOVE-CAREFULLY .VILLAIN> sets location=None,
    # stranding troll/thief/cyclops in limbo across sessions. Re-place them at their
    # canonical opening rooms, re-attach axe/knife, and clear runtime combat counters.
    troll = Object.global_objects.filter(name="troll", site=site).first()
    troll_room = Object.global_objects.filter(name="The Troll Room", site=site).first()
    axe = Object.global_objects.filter(name="bloody axe", site=site).first()
    if troll and troll_room:
        troll.location = troll_room
        troll.set_property("actorbit", True)
        troll.set_property("trytakebit", True)
        troll.set_property("open", True)
        troll.set_property("vbits", 0)
        troll.set_property("fights", 0)
        troll.save()
    if axe and troll:
        axe.location = troll
        axe.save()
    thief = Object.global_objects.filter(name="thief", site=site).first()
    round_room = Object.global_objects.filter(name="Round Room", site=site).first()
    knife = Object.global_objects.filter(name="nasty knife", site=site).first()
    stiletto = Object.global_objects.filter(name="stiletto", site=site).first()
    attic_room = Object.global_objects.filter(name="Attic", site=site).first()
    attic_table = (
        Object.global_objects.filter(name="table", site=site, location=attic_room).first() if attic_room else None
    )
    if thief and round_room:
        thief.location = round_room
        thief.set_property("actorbit", True)
        thief.set_property("contbit", True)
        thief.set_property("trytakebit", True)
        thief.set_property("open", True)
        thief.set_property("vbits", 0)
        thief.set_property("fights", 0)
        thief.save()
        # Empty the thief's pockets of everything except its own gear.
        # ROB / STEAL-JUNK accumulate treasures AND junk (tvalue=0 tools
        # like the wrench) into the thief across sessions.  The explicit
        # re-park lines above put every real object back at its canonical
        # room; anything still on the thief here is leftover loot that
        # would otherwise ride along forever — sweep it to limbo.  The
        # large bag is the thief's own container; sweep its contents too.
        for _carried in list(thief.contents.all()):
            if _carried == stiletto or _carried.name == "large bag":
                continue
            _carried.location = None
            _carried.save()
        _large_bag = Object.global_objects.filter(name="large bag", site=site).first()
        if _large_bag:
            for _bagged in list(_large_bag.contents.all()):
                _bagged.location = None
                _bagged.save()
    if stiletto and thief:
        stiletto.location = thief
        stiletto.save()
    if knife and attic_table:
        knife.location = attic_table
        knife.save()
    cyclops = Object.global_objects.filter(name="cyclops", site=site).first()
    cyclops_room = Object.global_objects.filter(name="Cyclops Room", site=site).first()
    if cyclops and cyclops_room:
        cyclops.location = cyclops_room
        cyclops.set_property("actorbit", True)
        cyclops.set_property("ndescbit", True)
        cyclops.set_property("trytakebit", True)
        cyclops.set_property("vbits", 0)
        cyclops.set_property("fights", 0)
        cyclops.save()
    # WINNER's STRENGTH defaults to 0 in ZIL (no explicit property on
    # ADVENTURER); arithmetic in FIGHT-STRENGTH/I-CURE/etc. requires the
    # property to exist so .getp("strength") returns 0 rather than None.
    wiz.set_property("strength", 0)
    wiz.save()
    # Canonical NPC strengths from dungeon.zil (CYCLOPS=10000, THIEF=5,
    # TROLL=2); the converter doesn't transfer the ZIL (STRENGTH N) literal
    # onto the generated object, so we seed them here.
    for _npc_name, _npc_strength in (("troll", 2), ("thief", 5), ("cyclops", 10000)):
        _npc = Object.global_objects.filter(name=_npc_name, site=site).first()
        if _npc:
            _npc.set_property("strength", _npc_strength)
            _npc.save()
    # Property-level grants.  Per property.py:87, set_property on an existing
    # Property row requires `write` on the Property itself — not just the
    # origin Object.  Initialize verbs grant on the Object; this loop covers
    # every Property of every substrate-classed instance with `everyone:write`,
    # idempotent via get_or_create.  Catches both bootstrap-defined and
    # reset-script-set properties so they're mutable by Adventurer at runtime.
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
    print("zork1 reset")


# When this file runs as part of the bootstrap (load_python in test fixtures
# / first-time moo_init), the zork1.local Site row may not yet exist — the
# reset only makes sense once the site has been created and populated.  Skip
# silently in that case so the bootstrap loader can proceed.
_site = Site.objects.filter(domain="zork1.local").first()
if _site is None:
    print("zork1 reset: site not yet created, skipping")
else:
    _reset_zork1_world(_site)
