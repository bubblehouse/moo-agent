#!/usr/bin/env python3
"""
build_from_yaml.py - Generic YAML-driven MOO environment builder.

Builds themed multi-room environments from YAML environment definitions.

Usage:
    python build_from_yaml.py environments/moes-tavern.yaml
    python build_from_yaml.py environments/planet-express/
    python build_from_yaml.py --dry-run environments/moes-tavern.yaml
    python build_from_yaml.py --no-test environments/moes-tavern.yaml
    python build_from_yaml.py --hash environments/moes-tavern.yaml
    python build_from_yaml.py --no-hash environments/moes-tavern.yaml

Requires:
    pip install pexpect pyyaml
    DjangoMOO running locally (docker-compose up)
"""

import argparse
import hashlib
import re
import sys
import time
from pathlib import Path

import yaml  # type: ignore[import-untyped]

# Add parent directory to path for moo_ssh import
sys.path.insert(0, str(Path(__file__).parent))
from moo_ssh import MooSSH  # pylint: disable=wrong-import-position

# Placeholder used in YAML names and verb code to mark where the hash suffix goes.
# With hash enabled:  "Room Name __hash_suffix__"  →  "Room Name [abc123]"
# With hash disabled: "Room Name __hash_suffix__"  →  "Room Name"
HASH_PLACEHOLDER = "__hash_suffix__"

# -----------------------------------------------------------------------------
# Hash Helper Functions
# -----------------------------------------------------------------------------


def apply_hash(text, run_hash, use_hash):
    """Replace __hash_suffix__ placeholder in text with the hash suffix or empty string."""
    if use_hash and run_hash:
        return text.replace(HASH_PLACEHOLDER, f"[{run_hash}]")
    else:
        # Remove the placeholder and any immediately preceding space
        return text.replace(f" {HASH_PLACEHOLDER}", "").replace(HASH_PLACEHOLDER, "")


def strip_hash_placeholder(text):
    """Remove the hash placeholder entirely, for use as an internal dictionary key."""
    return text.replace(f" {HASH_PLACEHOLDER}", "").replace(HASH_PLACEHOLDER, "")


# -----------------------------------------------------------------------------
# Helper Functions (reused from build_moes_tavern.py)
# -----------------------------------------------------------------------------


def obj_id(output):
    """Extract #N from @create output like 'Created #34 (bar stool)'."""
    m = re.search(r"Created (#\d+)", output)
    return m.group(1) if m else None


def create(moo, name, parent="$thing", obvious=False):
    """Create an object via @create and return its #N reference.

    Uses @create (not @eval create()) because @create output is captured
    synchronously via the ContextManager, while @eval output goes through
    player.tell() -> Kombu and arrives one command late.
    """
    escaped_name = name.replace('"', '\\"')
    escaped_parent = parent.replace('"', '\\"')
    output = moo.run(f'@create "{escaped_name}" from "{escaped_parent}" in the void')
    ref = obj_id(output)
    if not ref:
        print(f"  WARNING: could not get ID for '{name}' from: {output!r}", file=sys.stderr)
        return ref
    if obvious:
        moo.run(f'@eval "obj = lookup({ref[1:]}); obj.obvious = True; obj.save()"')
    return ref


def describe(moo, ref, desc):
    """Describe an object by #N reference (unambiguous)."""
    escaped_desc = desc.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')
    moo.run(f'@describe {ref} as "{escaped_desc}"')


def add_aliases(moo, ref, aliases):
    """Add aliases to an object using @alias verb."""
    for alias in aliases:
        escaped_alias = alias.replace('"', '\\"')
        moo.run(f'@alias {ref} as "{escaped_alias}"')


def move_to_room(moo, obj_ref, room_name):
    """
    Move an object from the void to a room using direct location assignment.

    Uses obj.location = room; obj.save() rather than moveto() so that
    $furniture objects (whose moveto verb returns False to block player takes)
    are still placed correctly by admin build code.

    obj_ref: #N reference (unquoted)
    room_name: full room name (with hash if applicable)
    """
    obj_id_num = obj_ref.replace("#", "")
    escaped_room = room_name.replace('"', '\\"')
    moo.run(f'@eval "obj = lookup({obj_id_num}); room = lookup(\\"{escaped_room}\\"); obj.location = room; obj.save()"')


def set_verb(moo, verb_name, obj_ref, code):
    """
    Create or update a verb using @edit ... with, passing multi-line code as
    a single \\n-escaped string. The @edit verb unescapes \\n back to newlines.

    obj_ref may be a #N id (not quoted) or a plain name (quoted).
    """
    # Escape backslashes first, then newlines, then double-quotes
    escaped = code.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')
    # #N refs are unquoted; plain names are quoted
    if str(obj_ref).startswith("#"):
        moo.run(f'@edit verb {verb_name} on {obj_ref} with "{escaped}"')
    else:
        moo.run(f'@edit verb {verb_name} on "{obj_ref}" with "{escaped}"')


# -----------------------------------------------------------------------------
# YAML Loading and Validation
# -----------------------------------------------------------------------------


def load_environment(yaml_path):
    """Load and validate YAML environment file or directory.

    If yaml_path is a directory, loads all *.yaml files from it and merges
    them into a single environment dict. Each file should contain one or more
    top-level sections (metadata, rooms, objects, npcs, verbs, test).
    """
    path = Path(yaml_path)

    if path.is_dir():
        env = {}
        section_files = sorted(path.glob("*.yaml"))
        if not section_files:
            raise ValueError(f"No .yaml files found in directory: {path}")
        for section_file in section_files:
            with open(section_file, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if data:
                env.update(data)
    else:
        with open(path, encoding="utf-8") as f:
            env = yaml.safe_load(f)

    # Validate required sections
    required = ["metadata", "rooms"]
    for section in required:
        if section not in env:
            raise ValueError(f"Missing required section: {section}")

    # Validate metadata fields
    metadata = env["metadata"]
    if "name" not in metadata:
        raise ValueError("metadata.name is required")

    return env


def generate_hash():
    """Generate unique 6-character hash for this build."""
    return hashlib.sha256(str(time.time()).encode()).hexdigest()[:6]


# -----------------------------------------------------------------------------
# Build Phase Functions
# -----------------------------------------------------------------------------


def teleport_to(moo, room_name):
    """Teleport the player to a room by name using @eval."""
    escaped = room_name.replace('"', '\\"')
    moo.run(f'@eval "context.player.location = lookup(\\"{escaped}\\"); context.player.save()"')


def build_rooms(moo, env, run_hash, use_hash):
    """
    Create all rooms and exits using a depth-first search traversal.

    Phase 1: Create every room in the void (no navigation required).
    Phase 2: DFS from the first room — teleport to each room, describe it,
             wire all its exits, then recurse into unvisited neighbors.

    The DFS approach prevents two classes of silent failure that occur with a
    flat YAML-order loop:

    1. @tunnel checks ``source.match_exit(direction)`` and silently returns
       early if that direction already exists. A flat loop that revisits an
       exit pair will drop one side with no error output.
    2. The ``created_exits`` set detects duplicate exit declarations in the
       YAML itself (same room + direction defined twice) and skips them with
       a warning rather than letting @tunnel silently fail.

    Rooms unreachable from the first room (disconnected subgraph) are detected
    and warned about, then still built so the environment is complete.

    room_map is keyed by the clean room name (placeholder stripped) and
    maps to the fully resolved name (with hash applied). Internal YAML
    references (exit to:, npc room:, object section keys) use clean names
    and look up via room_map.

    Returns: room_map dict {clean_name: resolved_name}
    """
    rooms_list = env["rooms"]
    room_map = {}  # clean_name -> resolved (hashed) name
    room_defs = {}  # clean_name -> room definition dict
    adjacency = {}  # clean_name -> [(direction, to_clean_name)]

    if not rooms_list:
        return room_map

    # Phase 1: Create all rooms in the void
    print("  Creating rooms:", file=sys.stderr)
    for room_def in rooms_list:
        clean_name = strip_hash_placeholder(room_def["name"])
        room_name = apply_hash(room_def["name"], run_hash, use_hash)
        room_map[clean_name] = room_name
        room_defs[clean_name] = room_def
        adjacency[clean_name] = [(e["direction"], e["to"]) for e in room_def.get("exits", [])]
        escaped = room_name.replace('"', '\\"')
        moo.run(f'@create "{escaped}" from "$room" in the void')
        print(f"    {room_name}", file=sys.stderr)

    # Phase 2: DFS — describe rooms and wire exits
    print("  Describing rooms and wiring exits (DFS):", file=sys.stderr)
    visited = set()
    created_exits = set()  # (clean_from, direction) pairs already tunnelled

    def dfs(clean_name):
        if clean_name in visited:
            return
        visited.add(clean_name)

        room_name = room_map[clean_name]
        room_def = room_defs[clean_name]

        # Teleport to this room and describe it
        teleport_to(moo, room_name)
        escaped_desc = room_def["description"].replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')
        moo.run(f'@describe here as "{escaped_desc}"')

        # In hash mode, alias the clean name so lookup("Room Name") works
        if use_hash and run_hash:
            escaped_clean = clean_name.replace('"', '\\"')
            moo.run(f'@alias here as "{escaped_clean}"')

        # Wire all exits for this room before recursing into neighbors.
        # Separating the two loops ensures we are still teleported to this
        # room when @tunnel runs — recursion would move us elsewhere.
        for direction, to_clean in adjacency[clean_name]:
            exit_key = (clean_name, direction)
            if exit_key in created_exits:
                print(
                    f"    SKIP duplicate exit: {clean_name} -{direction}-> (already wired)",
                    file=sys.stderr,
                )
                continue
            to_resolved = room_map.get(to_clean, to_clean)
            escaped_to = to_resolved.replace('"', '\\"')
            moo.run(f'@tunnel {direction} to "{escaped_to}"')
            created_exits.add(exit_key)
            print(f"    {room_name} -{direction}-> {to_resolved}", file=sys.stderr)

        # Recurse depth-first into unvisited neighbors (in YAML exit order)
        for _direction, to_clean in adjacency[clean_name]:
            if to_clean in room_defs and to_clean not in visited:
                dfs(to_clean)

    # Start DFS from the first room in the YAML list
    first_clean = strip_hash_placeholder(rooms_list[0]["name"])
    dfs(first_clean)

    # Detect and warn about rooms not reachable from the first room
    for clean_name in room_defs:
        if clean_name not in visited:
            print(
                f"  WARNING: '{clean_name}' is not reachable from '{first_clean}' — check exit definitions",
                file=sys.stderr,
            )
            dfs(clean_name)

    return room_map


def build_objects(moo, env, run_hash, use_hash, room_map):
    """
    Create all objects in all rooms.

    obj_refs is keyed by (clean_room_name, clean_obj_name) where both names
    have the hash placeholder stripped. Verb object: and room: fields use
    clean names and look up via this dict.

    Returns: obj_refs dict mapping (clean_room, clean_name) -> #N reference
    """
    obj_refs = {}
    objects = env.get("objects", {})
    parent = env["metadata"].get("base_parent", "$thing")

    for room_name, objs in objects.items():
        # room_name from YAML is a clean name (no placeholder)
        room_hash_name = room_map.get(room_name, room_name)
        refs_to_move = []

        print(f"  Creating objects for: {room_name}", file=sys.stderr)

        for obj_spec in objs:
            name = obj_spec["name"]
            clean_name = strip_hash_placeholder(name)
            desc = obj_spec.get("description", "")
            aliases = obj_spec.get("aliases", [])
            quantity = obj_spec.get("quantity", 1)
            obj_parent = obj_spec.get("parent", parent)
            obj_obvious = obj_spec.get("obvious", False)

            # Create object(s)
            for i in range(quantity):
                hash_name = apply_hash(name, run_hash, use_hash)
                ref = create(moo, hash_name, obj_parent, obvious=obj_obvious)

                if not ref:
                    continue

                # Only describe the first one
                if i == 0 and desc:
                    describe(moo, ref, desc)

                # In hash mode, prepend the clean name as an alias
                all_aliases = ([clean_name] + list(aliases)) if (use_hash and run_hash) else list(aliases)
                if all_aliases:
                    add_aliases(moo, ref, all_aliases)

                refs_to_move.append(ref)

                # Store ref for verb attachment (use first instance, keyed by clean name)
                if i == 0:
                    obj_refs[(room_name, clean_name)] = ref
                    print(f"    {ref}: {hash_name}", file=sys.stderr)

        # Move all objects to room
        for ref in refs_to_move:
            move_to_room(moo, ref, room_hash_name)

    return obj_refs


def create_player_record(moo, ref):
    """Create a Django Player record for an NPC object (no User, avatar only)."""
    obj_id_num = ref.replace("#", "")
    moo.run(
        f'@eval "from moo.core.models import Player; '
        f'obj = lookup({obj_id_num}); p = Player.objects.create(); p.avatar = obj; p.save()"'
    )


def build_npcs(moo, env, run_hash, use_hash, room_map):
    """Create all NPCs and move to rooms.

    npc_refs is keyed by clean NPC name (placeholder stripped).
    Each NPC gets a Django Player record (no User) so the object has full
    player infrastructure (tell, announce, etc.).
    """
    npcs = env.get("npcs", [])
    parent = env["metadata"].get("npc_parent", "$player")
    npc_refs = {}

    if not npcs:
        return npc_refs

    print("  Creating NPCs:", file=sys.stderr)

    for npc_spec in npcs:
        name = npc_spec["name"]
        clean_name = strip_hash_placeholder(name)
        hash_name = apply_hash(name, run_hash, use_hash)
        desc = npc_spec.get("description", "")
        aliases = npc_spec.get("aliases", [])
        room = npc_spec.get("room")

        ref = create(moo, hash_name, parent)

        if not ref:
            continue

        # Create a Player record (no User) so the NPC has full player infrastructure
        create_player_record(moo, ref)

        if desc:
            describe(moo, ref, desc)
        # In hash mode, prepend the clean name as an alias
        all_aliases = ([clean_name] + list(aliases)) if (use_hash and run_hash) else list(aliases)
        if all_aliases:
            add_aliases(moo, ref, all_aliases)
        if room:
            # room is a clean name (no placeholder)
            room_hash_name = room_map.get(room, room)
            move_to_room(moo, ref, room_hash_name)

        npc_refs[clean_name] = ref
        print(f"    {ref}: {hash_name}", file=sys.stderr)

    return npc_refs


def build_verbs(moo, env, run_hash, use_hash, obj_refs, npc_refs, room_map):
    """Attach verbs to objects/NPCs.

    verb object: fields may contain __hash_suffix__ (used for test verb lookup);
    the placeholder is stripped when looking up in obj_refs/npc_refs.
    Verb code has __hash_suffix__ replaced before being sent to the MOO.
    """
    verbs = env.get("verbs", [])

    if not verbs:
        return

    print("  Attaching verbs:", file=sys.stderr)

    for verb_spec in verbs:
        verb_name = verb_spec["verb"]
        obj_name = verb_spec["object"]
        obj_name_key = strip_hash_placeholder(obj_name)
        room_name = verb_spec.get("room")
        code = apply_hash(verb_spec["code"], run_hash, use_hash)

        # Resolve object reference
        obj_ref = None

        if room_name:
            # Use room context for disambiguation (room_name is a clean name)
            obj_ref = obj_refs.get((room_name, obj_name_key))
            if not obj_ref:
                # Try NPCs
                obj_ref = npc_refs.get(obj_name_key)
        else:
            # Search all rooms for object
            for (_, n), ref in obj_refs.items():
                if n == obj_name_key:
                    obj_ref = ref
                    break
            if not obj_ref:
                obj_ref = npc_refs.get(obj_name_key)

        # Also check if it's a room name (obj_name_key is a clean name)
        if not obj_ref and obj_name_key in room_map:
            obj_ref = f'"{room_map[obj_name_key]}"'

        if not obj_ref:
            print(f"    WARNING: Could not resolve object '{obj_name}' for verb '{verb_name}'", file=sys.stderr)
            continue

        set_verb(moo, verb_name, obj_ref, code)
        print(f"    {verb_name} on {obj_ref}", file=sys.stderr)


def generate_test_verb(env, run_hash, use_hash, room_map):
    """Generate test verb code from environment definition."""
    env_name = env["metadata"]["name"]
    test_name_base = env_name.lower().replace(" ", "-").replace("'", "")

    # Test verb name includes hash if enabled
    if use_hash and run_hash:
        test_name = f"test-{test_name_base}-{run_hash}"
    else:
        test_name = f"test-{test_name_base}"

    # Auto-generate test expectations from YAML structure
    test_spec = env.get("test", {})
    rooms = test_spec.get("rooms", [r["name"] for r in env.get("rooms", [])])
    objects = test_spec.get("objects", {})
    npcs = test_spec.get("npcs", [npc["name"] for npc in env.get("npcs", [])])
    verbs = test_spec.get("verbs", [])

    # Generate code using simplified template (no nested functions)
    code_parts = [
        "from moo.sdk import lookup, NoSuchObjectError, NoSuchVerbError",
        "",
        "passed = 0",
        "failed = 0",
        "",
        'print("[bold]--- Rooms ---[/bold]")',
        "rooms = {}",
    ]

    # Room checks — room names from YAML may contain __hash_suffix__
    for room_name in rooms:
        hash_name = apply_hash(room_name, run_hash, use_hash)
        escaped_hash_name = hash_name.replace('"', '\\"')
        display_name = strip_hash_placeholder(room_name)
        code_parts.append("try:")
        code_parts.append(f'    rooms["{display_name}"] = lookup("{escaped_hash_name}")')
        code_parts.append("    passed += 1")
        code_parts.append(f'    print(f"[green]PASS[/green] {display_name}")')
        code_parts.append("except NoSuchObjectError as e:")
        code_parts.append(f'    rooms["{display_name}"] = None')
        code_parts.append("    failed += 1")
        code_parts.append(f'    print(f"[red]FAIL[/red] {display_name}: {{e}}")')
        code_parts.append("")

    # Object checks
    if objects:
        code_parts.append('print("[bold]--- Objects ---[/bold]")')
        for room_name, obj_list in objects.items():
            # room_name here is a clean key
            code_parts.append(f'if rooms.get("{room_name}"):')
            code_parts.append(f'    names = [o.name for o in rooms["{room_name}"].contents.all()]')
            for obj_name in obj_list:
                code_parts.append(f'    if any("{obj_name}".lower() in n.lower() for n in names):')
                code_parts.append("        passed += 1")
                code_parts.append(f'        print(f"[green]PASS[/green] {room_name}: {obj_name}")')
                code_parts.append("    else:")
                code_parts.append("        failed += 1")
                code_parts.append(f'        print(f"[red]FAIL[/red] {room_name}: {obj_name} (not in {{names}})")')
            code_parts.append("")

    # NPC checks — NPC names from YAML may contain __hash_suffix__
    if npcs:
        code_parts.append('print("[bold]--- NPCs ---[/bold]")')
        for npc_name in npcs:
            hash_name = apply_hash(npc_name, run_hash, use_hash)
            escaped_hash_name = hash_name.replace('"', '\\"')
            display_name = strip_hash_placeholder(npc_name)
            code_parts.append("try:")
            code_parts.append(f'    lookup("{escaped_hash_name}")')
            code_parts.append("    passed += 1")
            code_parts.append(f'    print(f"[green]PASS[/green] {display_name}")')
            code_parts.append("except NoSuchObjectError as e:")
            code_parts.append("    failed += 1")
            code_parts.append(f'    print(f"[red]FAIL[/red] {display_name}: {{e}}")')
        code_parts.append("")

    # Verb checks — verb object: fields may contain __hash_suffix__
    if verbs:
        code_parts.append('print("[bold]--- Verbs ---[/bold]")')
        for verb_spec in verbs:
            obj_name = apply_hash(verb_spec["object"], run_hash, use_hash)
            escaped_obj_name = obj_name.replace('"', '\\"')
            verb_name = verb_spec["verb"]
            display_name = strip_hash_placeholder(verb_spec["object"])
            code_parts.append("try:")
            code_parts.append(f'    obj = lookup("{escaped_obj_name}")')
            code_parts.append(f'    obj.get_verb("{verb_name}")')
            code_parts.append("    passed += 1")
            code_parts.append(f'    print(f"[green]PASS[/green] {display_name}: {verb_name}")')
            code_parts.append("except NoSuchObjectError as e:")
            code_parts.append("    failed += 1")
            code_parts.append(f'    print(f"[red]FAIL[/red] {display_name}: {verb_name} (object not found: {{e}})")')
            code_parts.append("except NoSuchVerbError:")
            code_parts.append("    failed += 1")
            code_parts.append(f'    print(f"[red]FAIL[/red] {display_name}: {verb_name} (verb not found)")')
        code_parts.append("")

    code_parts.extend(
        [
            "total = passed + failed",
            'print(f"[bold]{passed}/{total} checks passed.[/bold]")',
        ]
    )

    return test_name, "\n".join(code_parts)


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Build MOO environment from YAML")
    parser.add_argument("yaml_file", help="Path to YAML environment file or directory")
    parser.add_argument("--dry-run", action="store_true", help="Parse YAML but don't connect to MOO")
    parser.add_argument("--no-test", action="store_true", help="Skip creating and running test verb")
    parser.add_argument("--hash", action="store_true", help="Force hash suffix mode (override YAML setting)")
    parser.add_argument("--no-hash", action="store_true", help="Force clean name mode (override YAML setting)")
    parser.add_argument("--host", default="localhost", help="MOO server hostname (default: localhost)")
    parser.add_argument("--port", type=int, default=8022, help="MOO server SSH port (default: 8022)")
    args = parser.parse_args()

    # Load environment
    try:
        env = load_environment(args.yaml_file)
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error loading YAML: {e}", file=sys.stderr)
        return 1

    env_name = env["metadata"]["name"]

    # Determine hash mode (metadata default, CLI override)
    use_hash = env["metadata"].get("use_hash_suffix", True)
    if args.hash:
        use_hash = True
    elif args.no_hash:
        use_hash = False

    if args.dry_run:
        print(f"Loaded environment: {env_name}")
        print(f"  Hash mode: {'enabled' if use_hash else 'disabled'}")
        print(f"  Rooms: {len(env.get('rooms', []))}")
        print(f"  Objects: {sum(len(objs) for objs in env.get('objects', {}).values())}")
        print(f"  NPCs: {len(env.get('npcs', []))}")
        print(f"  Verbs: {len(env.get('verbs', []))}")
        return 0

    # Generate hash only if needed
    run_hash = generate_hash() if use_hash else None

    hash_info = f" (run: {run_hash})" if run_hash else ""
    print(f"=== Building {env_name}{hash_info} ===", file=sys.stderr)

    try:
        with MooSSH(host=args.host, port=args.port) as moo:
            moo.enable_automation_mode()

            print("\n--- Phase 1: Rooms and exits ---", file=sys.stderr)
            room_map = build_rooms(moo, env, run_hash, use_hash)

            print("\n--- Phase 2: Objects ---", file=sys.stderr)
            obj_refs = build_objects(moo, env, run_hash, use_hash, room_map)

            print("\n--- Phase 3: NPCs ---", file=sys.stderr)
            npc_refs = build_npcs(moo, env, run_hash, use_hash, room_map)

            print("\n--- Phase 4: Verbs ---", file=sys.stderr)
            build_verbs(moo, env, run_hash, use_hash, obj_refs, npc_refs, room_map)

            if not args.no_test:
                print("\n--- Phase 5: Test verb ---", file=sys.stderr)
                test_name, test_code = generate_test_verb(env, run_hash, use_hash, room_map)
                set_verb(moo, test_name, "$programmer", test_code)

                print(f"\n--- Running {test_name} ---", file=sys.stderr)
                moo.run(test_name)

        print("\n=== Build complete. ===", file=sys.stderr)
        if not args.no_test:
            print(f"Test verb: {test_name}", file=sys.stderr)

        return 0

    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"\n=== Build failed: {e} ===", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
