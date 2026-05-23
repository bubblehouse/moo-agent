"""
Stage-2 PydanticAI tools — one async function per MOO command an agent can issue.

Each tool follows the same shape:

1. Build the command string (translate logic, ported verbatim from the old
   ``tools.py`` ``ToolSpec.translate`` callables).
2. ``await ctx.deps.limiter.wait()`` to respect the per-agent rate cap.
3. ``await ctx.deps.connection.request(cmd, async_wait_s=..., async_pattern=...)``
   per the spec table in ``docs/specs/pydantic-ai-stage-2.md``.
4. ``ctx.deps.on_window_append(f"> {cmd}")`` so the brain's rolling window
   reflects what was sent.
5. Return the resulting MOO output string to the model.

Side-effecting tools (``respond``, ``done``, ``teleport``, ``page``) follow
slightly different shapes — see each function's docstring.

The async-wait patterns for Celery-backed verbs live here as module-level
``re.Pattern`` constants. Their meanings are documented in the spec.
"""

import json
import re
import time

from pydantic_ai import RunContext, Tool

from moo.agent.brain.deps import BrainDeps


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _norm_ref(value: str) -> str:
    """Rewrite a bare integer like ``"22"`` to ``"#22"``; pass other strings through."""
    s = str(value).strip()
    if s.isdigit():
        return f"#{s}"
    return s


def _log_call(ctx: "RunContext[BrainDeps]", **kwargs) -> None:
    """
    Emit a ``[Tool] name(arg=value, ...)`` thought so the operator can see what
    the model called this turn. The old ``_dispatch_actions`` path emitted
    this for every action; Stage-2 tools restore the same visibility from
    inside the tool body.
    """
    args = ", ".join(f"{k}={v!r}" for k, v in kwargs.items())
    # PydanticAI guarantees RunContext.tool_name during a tool dispatch; no
    # defensive fallback — a future rename surfaces in tests.
    ctx.deps.on_thought(f"[Tool] {ctx.tool_name}({args})")


async def _dispatch(
    ctx: "RunContext[BrainDeps]",
    cmd: str,
    *,
    async_wait_s: float = 0.0,
    async_pattern: "re.Pattern[str] | None" = None,
) -> str:
    """The send-and-record core that every dispatching tool shares.

    Rate-limits the call, sends the command via the side-channel request, and
    appends the ``> {cmd}`` marker into the brain's rolling window so the next
    LLM cycle sees what was sent. Lifted out of every tool body so a future
    change to the dispatch contract (e.g. per-tool span attributes,
    instrumentation, return shaping) lands in one place instead of 25.
    """
    await ctx.deps.limiter.wait()
    result = await ctx.deps.connection.request(cmd, async_wait_s=async_wait_s, async_pattern=async_pattern)
    ctx.deps.on_window_append(f"> {cmd}")
    return result


# Board/Book tools require the agent to be in The Agency; auto-prefix saves
# the model from re-learning that on every call.
_AGENCY_TELEPORT = 'teleport "The Agency"'


# ---------------------------------------------------------------------------
# Async-wait patterns for Celery-backed verbs (spec table lines 142-153)
# ---------------------------------------------------------------------------

_DIG_SUCCESS_RE = re.compile(r'^Dug an exit \w+ to "([^"]+)"')
_BURROW_SUCCESS_RE = re.compile(r"^You are now in [^(]+\(#\d+\)\.")
_CREATE_SUCCESS_RE = re.compile(r"^(?:Created|Transmuted) #\d+")
_EDIT_VERB_SUCCESS_RE = re.compile(r"^(?:Created verb|Set verb)")
_SET_SUCCESS_RE = re.compile(r"^Set ")
_ALIAS_SUCCESS_RE = re.compile(r"^Added alias")


# ---------------------------------------------------------------------------
# World-building tools
# ---------------------------------------------------------------------------


async def dig(ctx: RunContext[BrainDeps], direction: str, room_name: str) -> str:
    """Create a new exit from the current room to a new destination room. Does NOT move you — always follow with go()."""
    direction = direction.strip()
    room_name = room_name.strip().strip('"')
    _log_call(ctx, direction=direction, room_name=room_name)
    return await _dispatch(ctx, f'@dig {direction} to "{room_name}"', async_wait_s=3.0, async_pattern=_DIG_SUCCESS_RE)


async def go(ctx: RunContext[BrainDeps], direction: str) -> str:
    """Move through an exit in the given direction."""
    _log_call(ctx, direction=direction)
    return await _dispatch(ctx, f"go {direction.strip()}")


async def describe(ctx: RunContext[BrainDeps], target: str, text: str) -> str:
    """Set the description of an object or room."""
    target = _norm_ref(target)
    text = text.strip().strip('"')
    _log_call(ctx, target=target, text=text)
    return await _dispatch(ctx, f'@describe {target} as "{text}"')


async def create_object(ctx: RunContext[BrainDeps], name: str, parent: str = "$thing") -> str:
    """Create a new object in the current room. Parent defaults to '$thing'; pass '$container', '$exit', etc. for other classes."""
    name = name.strip().strip('"')
    parent = (parent or "$thing").strip().strip('"') or "$thing"
    _log_call(ctx, name=name, parent=parent)
    return await _dispatch(
        ctx, f'@create "{name}" from "{parent}" in here', async_wait_s=3.0, async_pattern=_CREATE_SUCCESS_RE
    )


async def write_verb(
    ctx: RunContext[BrainDeps],
    obj: str,
    verb: str,
    code: str,
    dspec: str = "none",
    on: str = "$thing",
) -> str:
    """Create or overwrite a verb on an object. Handles the shebang header automatically — provide only the Python verb body in 'code'. 'on' is the parent class for argument dispatch (default '$thing'); pass '$exit', '$container', '$room', etc. for verbs whose first argument is that type."""
    obj = _norm_ref(obj)
    verb = verb.strip()
    dspec = (dspec or "none").strip() or "none"
    on = (on or "$thing").strip() or "$thing"
    _log_call(ctx, obj=obj, verb=verb, dspec=dspec, on=on, code=f"<{len(code)} chars>")
    source = f"#!moo verb {verb} --on {on} --dspec {dspec}\n{code}"
    cmd = f"@edit verb {verb} on {obj} with {json.dumps(source)}"
    return await _dispatch(ctx, cmd, async_wait_s=3.0, async_pattern=_EDIT_VERB_SUCCESS_RE)


async def look(ctx: RunContext[BrainDeps], target: str = "") -> str:
    """Look at the current room or a specific object. Target must be an object name or '#N'. To test a verb, send the verb command directly (e.g. 'pry #949') via raw(), not look()."""
    target = _norm_ref(target or "")
    _log_call(ctx, target=target)
    return await _dispatch(ctx, f"look {target}".rstrip() if target else "look")


async def alias(ctx: RunContext[BrainDeps], obj: str, name: str) -> str:
    """Add an alias name to an object so players can refer to it by that name."""
    obj = _norm_ref(obj)
    name = name.strip().strip('"')
    _log_call(ctx, obj=obj, name=name)
    return await _dispatch(ctx, f'@alias {obj} as "{name}"', async_wait_s=2.0, async_pattern=_ALIAS_SUCCESS_RE)


async def obvious(ctx: RunContext[BrainDeps], obj: str) -> str:
    """Mark an object as obvious so it appears in room descriptions."""
    obj = _norm_ref(obj)
    _log_call(ctx, obj=obj)
    return await _dispatch(ctx, f"@obvious {obj}", async_wait_s=2.0, async_pattern=_SET_SUCCESS_RE)


async def move_object(ctx: RunContext[BrainDeps], obj: str, destination: str) -> str:
    """Move an object to a different room or container (changes its location). Do NOT use this for spatial placement — use place() instead."""
    obj = _norm_ref(obj)
    destination = _norm_ref(destination)
    _log_call(ctx, obj=obj, destination=destination)
    return await _dispatch(ctx, f"@move {obj} to {destination}")


async def place(ctx: RunContext[BrainDeps], obj: str, prep: str, target: str) -> str:
    """Set a spatial relationship between an object and a target in the same room. Stores metadata only — the object stays in the room. NEVER use move_object() for this. Valid preps: 'on', 'under', 'behind', 'before', 'beside', 'over'."""
    obj = _norm_ref(obj)
    target = _norm_ref(target)
    _log_call(ctx, obj=obj, prep=prep, target=target)
    return await _dispatch(ctx, f"place {obj} {prep.strip().lower()} {target}")


async def open_(ctx: RunContext[BrainDeps], obj: str) -> str:
    """Open a container or door."""
    obj = _norm_ref(obj)
    _log_call(ctx, obj=obj)
    return await _dispatch(ctx, f"open {obj}")


async def close_(ctx: RunContext[BrainDeps], obj: str) -> str:
    """Close a container or door."""
    obj = _norm_ref(obj)
    _log_call(ctx, obj=obj)
    return await _dispatch(ctx, f"close {obj}")


async def put(ctx: RunContext[BrainDeps], item: str, container: str) -> str:
    """Put an item inside a container (moves it into the container). The container must be open. NOT the same as place() — put() changes containment, place() sets spatial metadata."""
    item = _norm_ref(item)
    container = _norm_ref(container)
    _log_call(ctx, item=item, container=container)
    return await _dispatch(ctx, f"put {item} in {container}")


async def take(ctx: RunContext[BrainDeps], item: str, source: str = "") -> str:
    """Take an item from the room into your inventory. Optionally specify a source container to take from."""
    item = _norm_ref(item)
    source = _norm_ref(source or "")
    _log_call(ctx, item=item, source=source)
    return await _dispatch(ctx, f"take {item} from {source}" if source else f"take {item}")


async def drop(ctx: RunContext[BrainDeps], obj: str) -> str:
    """Drop an item from inventory into the current room."""
    obj = _norm_ref(obj)
    _log_call(ctx, obj=obj)
    return await _dispatch(ctx, f"drop {obj}")


async def tunnel(ctx: RunContext[BrainDeps], direction: str, destination: str) -> str:
    """Add a return exit from the current room back to an origin room. Use immediately after dig() and go() to wire the exit in both directions. Always use #N for destination — never a room name."""
    direction = direction.strip()
    destination = _norm_ref(destination)
    _log_call(ctx, direction=direction, destination=destination)
    return await _dispatch(
        ctx, f"@tunnel {direction} to {destination}", async_wait_s=3.0, async_pattern=_DIG_SUCCESS_RE
    )


async def show(ctx: RunContext[BrainDeps], target: str = "here") -> str:
    """Inspect an object or the current room in full detail — exits, contents, properties, verbs, IDs. Prefer survey() for routine checks (smaller output)."""
    target = _norm_ref(target or "here")
    _log_call(ctx, target=target)
    return await _dispatch(ctx, f"@show {target}")


async def survey(ctx: RunContext[BrainDeps], target: str = "") -> str:
    """Lightweight room inspector. Returns only the room name, exits with #N IDs, and a flat contents list (~5 lines). Use instead of show() to avoid context overload."""
    target = _norm_ref(target or "")
    _log_call(ctx, target=target)
    return await _dispatch(ctx, f"@survey {target}".rstrip() if target else "@survey")


async def rooms(ctx: RunContext[BrainDeps]) -> str:
    """List every room instance in the world as a flat #N/name list. Use at session start to build a traversal plan."""
    _log_call(ctx)
    return await _dispatch(ctx, "@rooms")


async def divine(ctx: RunContext[BrainDeps], subject: str = "location", of: str = "") -> str:
    """Consult the aether for random world objects.
    divine(subject='location') returns random rooms including disconnected areas.
    divine(subject='child', of='$thing') returns three random descendants of the given class.
    divine(subject='location', of='#317') walks up containers from #317 to its enclosing $room subclass."""
    subject = (subject or "location").strip() or "location"
    of_target = (of or "").strip()
    _log_call(ctx, subject=subject, of=of_target)
    return await _dispatch(ctx, f"@divine {subject} of {of_target}" if of_target else f"@divine {subject}")


async def exits(ctx: RunContext[BrainDeps], target: str = "here") -> str:
    """Show the exits for a room. Accepts 'here', '#N', or a room name. Use before @burrow or @dig to check which directions are already taken."""
    target = _norm_ref(target or "here")
    _log_call(ctx, target=target)
    return await _dispatch(ctx, f"@exits {target}")


async def teleport(ctx: RunContext[BrainDeps], destination: str) -> str:
    """Teleport directly to a room by #N or name, without following exit chains. Use instead of chaining go() commands for long-range navigation."""
    dest = _norm_ref(destination)
    _log_call(ctx, destination=dest)
    # Read live state so a second teleport in the same agent.run() cycle sees
    # the room the first teleport landed in, not the stale entry-snapshot.
    here_id = ctx.deps.state.current_room_id
    here_name = ctx.deps.state.current_room_name
    if here_id and (dest == here_id or (here_name and dest.lower() == here_name.lower())):
        # Redundant teleport — surface the skip to the model so it advances
        # to the next plan step rather than re-issuing the same destination.
        msg = f"[Skipped] Already in {here_name} ({here_id}). Pick the next step from your plan instead of teleporting."
        ctx.deps.on_thought(msg)
        return msg
    return await _dispatch(ctx, f"teleport {dest}")


async def burrow(ctx: RunContext[BrainDeps], direction: str, room_name: str) -> str:
    """Atomic bidirectional dig: creates a forward exit to a new room, moves you into it, and wires the return exit automatically (opposite direction). Use instead of dig() + go() + tunnel() to avoid wiring errors."""
    direction = direction.strip()
    room_name = room_name.strip().strip('"')
    _log_call(ctx, direction=direction, room_name=room_name)
    return await _dispatch(
        ctx, f'@burrow {direction} to "{room_name}"', async_wait_s=3.0, async_pattern=_BURROW_SUCCESS_RE
    )


async def done(ctx: RunContext[BrainDeps], summary: str) -> str:
    """Signal that the current goal is fully complete. Brain consumes the summary and exits the cycle — no MOO command is sent."""
    _log_call(ctx, summary=summary)
    ctx.deps.session_done = True
    ctx.deps.pending_done_msg = summary
    return "Session marked done."


async def page(ctx: RunContext[BrainDeps], target: str, message: str) -> str:
    """Send a page (private message) to another player. Used for Token Protocol handoffs. When sending 'Token:' messages, include the room list in the body."""
    target = target.strip()
    message_clean = message.replace("\n", " ").strip()
    _log_call(ctx, target=target, message=message_clean)
    result = await _dispatch(ctx, f"page {target} with {message_clean}")
    target_l = target.lower()
    if "Token:" in message_clean and target_l and target_l != "foreman":
        ctx.deps.token_dispatched_at = time.monotonic()
        ctx.deps.token_dispatched_to = target
        ctx.deps.on_thought(f"[Stall] Token dispatched to {target} — stall timer started.")
    if "Token:" in message_clean and target_l == "foreman" and "done" in message_clean.lower():
        ctx.deps.foreman_paged = True
    return result


# ---------------------------------------------------------------------------
# Dispatch Board / Survey Book tools — auto-prefixed with a teleport to The
# Agency since these commands fail with "Huh?" from anywhere else.
# ---------------------------------------------------------------------------


async def _ensure_in_agency(ctx: RunContext[BrainDeps]) -> None:
    """Dispatch the agency-teleport prefix shared by board/book tools."""
    await _dispatch(ctx, _AGENCY_TELEPORT)


async def post_board(ctx: RunContext[BrainDeps], topic: str, room_ids: str) -> str:
    """Post a room ID list to The Dispatch Board for a specific topic. Mason calls this before passing the token so workers know which rooms to visit. Auto-teleports to The Agency first."""
    topic = topic.strip().lower()
    room_ids = room_ids.strip()
    _log_call(ctx, topic=topic, room_ids=room_ids)
    await _ensure_in_agency(ctx)
    return await _dispatch(ctx, f'post on "The Dispatch Board" under {topic} with "{room_ids}"')


async def read_board(ctx: RunContext[BrainDeps], topic: str) -> str:
    """Read the room ID list from The Dispatch Board for a specific topic. Workers call this on token receipt to get the rooms Mason built. Auto-teleports to The Agency first."""
    topic = topic.strip().lower()
    _log_call(ctx, topic=topic)
    await _ensure_in_agency(ctx)
    return await _dispatch(ctx, f'read "The Dispatch Board" under {topic}')


async def write_book(ctx: RunContext[BrainDeps], room_id: str, topic: str, entry: str) -> str:
    """Write an entry to The Survey Book for a specific room and topic. Call after finishing all rooms and returning to The Agency. Auto-teleports first."""
    room_id = room_id.strip()
    topic = topic.strip().lower()
    entry = entry.replace("\n", " ").strip()
    _log_call(ctx, room_id=room_id, topic=topic, entry=entry)
    await _ensure_in_agency(ctx)
    return await _dispatch(ctx, f'write in "The Survey Book" under {topic} with "{room_id}: {entry}"')


async def read_book(ctx: RunContext[BrainDeps], topic: str, room_id: str = "") -> str:
    """Read entries from The Survey Book for a specific topic. Optionally filter to a single room. Auto-teleports first."""
    topic = topic.strip().lower()
    room_id = room_id.strip()
    _log_call(ctx, topic=topic, room_id=room_id)
    await _ensure_in_agency(ctx)
    cmd = f'read "The Survey Book" under {topic} from {room_id}' if room_id else f'read "The Survey Book" under {topic}'
    return await _dispatch(ctx, cmd)


async def clear_topic(ctx: RunContext[BrainDeps], topic: str) -> str:
    """Clear The Dispatch Board and Survey Book entries for a specific topic. Foreman calls this at the end of each full chain loop. Auto-teleports first."""
    topic = topic.strip().lower()
    _log_call(ctx, topic=topic)
    await _ensure_in_agency(ctx)
    r1 = await _dispatch(ctx, f'erase "The Dispatch Board" under {topic}')
    r2 = await _dispatch(ctx, f'erase "The Survey Book" under {topic}')
    return f"{r1}\n{r2}"


# ---------------------------------------------------------------------------
# System tools — available to every agent regardless of config
# ---------------------------------------------------------------------------


async def raw(ctx: RunContext[BrainDeps], command: str) -> str:
    """Send a raw MOO command verbatim. Use ONLY for commands that have no dedicated tool, e.g. '@realm $room', '@eval ...', '@recycle #N'."""
    command = str(command or "").strip()
    _log_call(ctx, command=command)
    if not command:
        return ""
    return await _dispatch(ctx, command)


async def respond(ctx: RunContext[BrainDeps], message: str) -> str:
    """Say something without acting on the environment. Use when you have an observation, a question, or nothing to do this cycle. No MOO command is sent."""
    msg = (message or "").strip()
    _log_call(ctx, message=msg)
    if msg:
        ctx.deps.on_thought(f"[Respond] {msg}")
    ctx.deps.respond_count += 1
    # Escalating nudge: a model stuck in a respond-loop sees a stronger and
    # stronger hint to either act or emit final_result, before the hard
    # ``tool_calls_per_cycle`` cap fires.
    if ctx.deps.respond_count >= 3:
        return (
            f"Acknowledged. NOTE: you have called respond() {ctx.deps.respond_count} "
            "times this cycle without acting on the world or emitting a final "
            "result. Stop calling respond(). Either take a concrete action via "
            "another tool, or emit your final AgentResponse now to end the cycle."
        )
    if ctx.deps.respond_count == 2:
        return (
            "Acknowledged. You have now called respond() twice this cycle. "
            "If there is nothing to act on, emit your final AgentResponse to "
            "end the cycle rather than calling respond() again."
        )
    return "Acknowledged."


# ---------------------------------------------------------------------------
# Registry — passed to ``Agent(tools=ALL_TOOLS)`` in ``make_agent``.
# ---------------------------------------------------------------------------


# open/close are Python builtins; we define them as ``open_``/``close_`` here
# and wrap them as Tool objects with the original tool names so the model and
# SOULs see ``open(obj)`` / ``close(obj)``.
ALL_TOOLS = [
    dig,
    go,
    describe,
    create_object,
    write_verb,
    look,
    alias,
    obvious,
    move_object,
    place,
    Tool(open_, name="open"),
    Tool(close_, name="close"),
    put,
    take,
    drop,
    tunnel,
    show,
    survey,
    rooms,
    divine,
    exits,
    teleport,
    burrow,
    done,
    page,
    post_board,
    read_board,
    write_book,
    read_book,
    clear_topic,
    raw,
    respond,
]


def _tool_name(entry) -> str:
    """The advertised name of an ``ALL_TOOLS`` entry — handles plain functions
    and ``Tool``-wrapped entries (used for ``open``/``close`` so they don't
    shadow Python builtins)."""
    if isinstance(entry, Tool):
        return entry.name
    return entry.__name__


ALL_TOOLS_BY_NAME: dict[str, object] = {_tool_name(t): t for t in ALL_TOOLS}

# ``raw`` and ``respond`` are always available regardless of per-agent config —
# every agent needs an escape hatch and a no-op channel. Matches the
# pre-Stage-2 invariant from the old ``tools.py``/``brain`` merge logic.
SYSTEM_TOOL_NAMES: tuple[str, ...] = ("raw", "respond")


def select_tools(names: list[str] | None) -> list[object]:
    """
    Build the agent's tool list from a per-agent whitelist. ``names=None``
    returns every tool; a non-empty list returns those plus the always-on
    ``raw``/``respond`` tools. Unknown names are dropped silently — the caller
    is expected to surface them as a config warning via ``on_thought``.
    """
    if names is None:
        return list(ALL_TOOLS)
    seen: set[str] = set()
    selected: list[object] = []
    for n in list(names) + list(SYSTEM_TOOL_NAMES):
        if n in seen or n not in ALL_TOOLS_BY_NAME:
            continue
        seen.add(n)
        selected.append(ALL_TOOLS_BY_NAME[n])
    return selected
