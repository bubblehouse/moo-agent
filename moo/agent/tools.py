"""
Tool harness for moo-agent.

Defines ToolParam, ToolSpec, LLMResponse, and the BUILDER_TOOLS registry.
ToolSpec.translate() converts validated argument dicts to MOO command strings,
keeping command syntax out of the LLM's output path.

Does not import from moo.core or trigger Django setup.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Callable


def _norm_ref(value: str) -> str:
    """
    Normalize an object reference arg so a bare integer like "22" becomes "#22".

    LLMs routinely emit ``target=22`` or ``obj=22`` as tool args, which translate
    to ``@survey 22`` / ``@move 22 to ...``. The MOO parser then tries to look
    up an object literally named "22" in the current room and fails with
    "There is no '22' here." Normalizing at tool translation time eliminates
    the entire class of error without burdening the agents with a guidance rule.

    Passthrough for anything that is not a bare positive integer — ``#22``,
    ``here``, ``$player_start``, ``"mahogany desk"``, etc. are left alone.
    """
    s = str(value).strip()
    if s.isdigit():
        return f"#{s}"
    return s


@dataclass
class ToolParam:
    name: str
    type: str  # "string" | "integer" | "boolean"
    description: str
    required: bool = True
    default: str = ""


@dataclass
class ToolSpec:
    """
    A single typed tool the agent can call.

    translate() accepts a dict of validated arguments and returns the list of
    MOO commands to execute in order (empty list means no commands, e.g. 'done').
    """

    name: str
    description: str
    params: list[ToolParam]
    translate: Callable[[dict], list[str]]

    def to_anthropic_schema(self) -> dict:
        """Return the Anthropic tool schema dict for this spec."""
        required = [p.name for p in self.params if p.required]
        properties = {}
        for p in self.params:
            prop: dict = {"type": p.type, "description": p.description}
            if p.default:
                prop["default"] = p.default
            properties[p.name] = prop
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        }

    def to_openai_schema(self) -> dict:
        """Return the OpenAI-compatible function schema for LM Studio."""
        required = [p.name for p in self.params if p.required]
        properties = {}
        for p in self.params:
            prop: dict = {"type": p.type, "description": p.description}
            if p.default:
                prop["default"] = p.default
            properties[p.name] = prop
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }


@dataclass
class LLMResponse:
    """
    Unified response from any LLM provider.

    text holds concatenated TextBlock content (reasoning, GOAL:, SOUL_PATCH_* etc.).
    tool_calls holds structured tool invocations as (name, input_dict) pairs.
    """

    text: str
    tool_calls: list[tuple[str, dict]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Tool string parser for LM Studio text-based fallback
# ---------------------------------------------------------------------------

# Format 1 (explicit prefix):  TOOL: name(key="value" key2="value2")
_TOOL_LINE_RE = re.compile(r"^TOOL:\s*(\w+)\(([^)]*)\)\s*$")

# Format 2 (Gemma 4 native):   call:name{...}  or  tool_call:name{...}  or  tool_code:name(...)
# Gemma 4 emits tool calls in its text content using these prefixes when
# LM Studio does not expose them via the OpenAI tool_calls field.
_GEMMA_CALL_RE = re.compile(
    r"^(?:TOOL_CALL|tool_call|tool_code|tool_use|call):\s*(\w+)\s*[\{\(](.*?)[\}\)]\s*$", re.DOTALL
)

# Format 3 (bare Python-style call, no prefix): move_object(obj="#44", destination="#41")
# Used when the model puts tool calls inside a SCRIPT: block without prefix.
_BARE_CALL_RE = re.compile(r"^(\w+)\s*\(([^)]*)\)\s*$")

# Gemma wraps string values in <|"|> ... <|"|> special tokens.
# Strip them before extracting key-value pairs.
_GEMMA_STR_TOKEN_RE = re.compile(r"<\|[\"']\|>(.*?)<\|[\"']\|>")

# Key-value extractor: handles key="val", key='val', key: "val", key: 'val', key: val
_KV_RE = re.compile(r'(\w+)\s*[:=]\s*(?:"([^"]*?)"|\'([^\']*?)\'|([^\s,}]+))')


def _strip_gemma_tokens(s: str) -> str:
    """Replace Gemma pipe-quoted token wrappers with plain quoted values."""
    return _GEMMA_STR_TOKEN_RE.sub(r'"\1"', s)


def parse_tool_line(line: str, known_names: "set[str] | None" = None) -> tuple[str, dict] | None:
    """
    Parse a tool-call directive from an LM Studio response line.

    Returns (tool_name, args_dict) or None if the line doesn't match.

    Supported formats:
      TOOL: dig(direction="north" room_name="The Library")
      call:dig{direction: "north", room_name: "The Library"}
      tool_call:dig{direction: north, room_name: The Library}  (Gemma pipe-token wrapped)
      move_object(obj="#44", destination="#41")  bare call, validated against known_names
    """
    stripped = line.strip()
    m = _TOOL_LINE_RE.match(stripped) or _GEMMA_CALL_RE.match(stripped)
    if not m:
        # Try bare Python-style call only when a known-names set is supplied,
        # to avoid misidentifying MOO commands that happen to contain parentheses.
        bare = _BARE_CALL_RE.match(stripped)
        if bare and known_names is not None and bare.group(1) in known_names:
            m = bare
        else:
            return None
    name = m.group(1)
    kv_str = _strip_gemma_tokens(m.group(2))
    args: dict[str, str] = {}
    for kv_match in _KV_RE.finditer(kv_str):
        key = kv_match.group(1)
        # Take whichever capture group matched
        value = kv_match.group(2) or kv_match.group(3) or kv_match.group(4) or ""
        args[key] = value
    return name, args


# ---------------------------------------------------------------------------
# Registry lookup
# ---------------------------------------------------------------------------


def get_tool(registry: "list[ToolSpec]", name: str) -> "ToolSpec | None":
    """Return the ToolSpec with the given name, or None."""
    for spec in registry:
        if spec.name == name:
            return spec
    return None


# ---------------------------------------------------------------------------
# BUILDER_TOOLS — standard tools for environment construction
# ---------------------------------------------------------------------------


def _dig(args: dict) -> list[str]:
    direction = args["direction"].strip()
    room_name = args["room_name"].strip().strip('"')
    return [f'@dig {direction} to "{room_name}"']


_VALID_DIRECTIONS = {
    "north",
    "south",
    "east",
    "west",
    "up",
    "down",
    "northeast",
    "northwest",
    "southeast",
    "southwest",
    "ne",
    "nw",
    "se",
    "sw",
}


def _go(args: dict) -> list[str]:
    raw = args.get("direction", "").strip().lower().lstrip("#")
    if not raw:
        return ['say ERROR: go() requires a direction argument, e.g. go(direction="north")']
    # Reject room IDs passed as directions (e.g. "#41" or "41")
    if raw.isdigit() or raw not in _VALID_DIRECTIONS:
        return [f'say ERROR: go() requires a compass direction (north/south/east/west/up/down), not "{raw}"']
    return [f"go {raw}"]


def _describe(args: dict) -> list[str]:
    target = _norm_ref(args["target"])
    text = args["text"].strip().strip('"')
    return [f'@describe {target} as "{text}"']


def _create_object(args: dict) -> list[str]:
    name = args["name"].strip().strip('"')
    parent = args.get("parent", "$thing").strip().strip('"') or "$thing"
    # "in here" places the object directly in the current room (bypasses inventory).
    return [f'@create "{name}" from "{parent}" in here']


def _write_verb(args: dict) -> list[str]:
    obj = _norm_ref(args["obj"])
    verb = args["verb"].strip()
    dspec = args.get("dspec", "none").strip() or "none"
    code = args["code"]
    # Build the full verb source: shebang + code.
    # parse_shebang() only reads the FIRST LINE, so all flags must be on it.
    # --on $thing is required by parse_shebang (marked required=True in argparse).
    # json.dumps produces a double-quoted string with \n for newlines;
    # at_edit.py expands those back to real newlines before calling parse_shebang.
    # @edit syntax: @edit verb <name> on <obj> with <content>
    source = f"#!moo verb {verb} --on $thing --dspec {dspec}\n{code}"
    quoted = json.dumps(source)
    return [f"@edit verb {verb} on {obj} with {quoted}"]


def _set_property(args: dict) -> list[str]:
    obj = _norm_ref(args["obj"])
    prop = args["prop"].strip()
    value = args["value"].strip()
    return [f"@set {obj}.{prop} to {value}"]


def _look(args: dict) -> list[str]:
    target = _norm_ref(args.get("target") or "")
    return [f"look {target}".rstrip()] if target else ["look"]


def _alias(args: dict) -> list[str]:
    obj = _norm_ref(args["obj"])
    name = args["name"].strip().strip('"')
    return [f'@alias {obj} as "{name}"']


def _obvious(args: dict) -> list[str]:
    obj = _norm_ref(args["obj"])
    return [f"@obvious {obj}"]


def _move_object(args: dict) -> list[str]:
    obj = _norm_ref(args["obj"])
    destination = _norm_ref(args["destination"])
    return [f"@move {obj} to {destination}"]


def _show(args: dict) -> list[str]:
    target = _norm_ref(args.get("target") or "here")
    return [f"@show {target}"]


def _tunnel(args: dict) -> list[str]:
    direction = args["direction"].strip()
    destination = _norm_ref(args["destination"])
    return [f"@tunnel {direction} to {destination}"]


def _survey(args: dict) -> list[str]:
    target = _norm_ref(args.get("target") or "")
    return [f"@survey {target}".rstrip()] if target else ["@survey"]


def _rooms(_args: dict) -> list[str]:
    return ["@rooms"]


def _divine(args: dict) -> list[str]:
    subject = str(args.get("subject", "location")).strip() or "location"
    of_target = str(args.get("of", "")).strip()
    if of_target:
        return [f"@divine {subject} of {of_target}"]
    return [f"@divine {subject}"]


def _exits(args: dict) -> list[str]:
    target = _norm_ref(args.get("target") or "here")
    return [f"@exits {target}"]


def _teleport(args: dict) -> list[str]:
    destination = _norm_ref(args["destination"])
    return [f"teleport {destination}"]


def _burrow(args: dict) -> list[str]:
    direction = args["direction"].strip()
    room_name = args["room_name"].strip().strip('"')
    return [f'@burrow {direction} to "{room_name}"']


def _done(_args: dict) -> list[str]:
    # Brain intercepts the 'done' tool call to update goal state; no MOO command.
    return []


def _page(args: dict) -> list[str]:
    target = args["target"].strip()
    message = args.get("message", "").replace("\n", " ").strip()
    return [f"page {target} with {message}"]


def _send_report(args: dict) -> list[str]:
    body = args.get("body", "").replace("\n", " ").strip()
    return [f'@send foreman with "Subject: Work Report\\n\\n{body}"']


def _post_board(args: dict) -> list[str]:
    topic = args.get("topic", "").strip().lower()
    rooms = args.get("rooms", "").strip()
    return [f'post on "The Dispatch Board" under {topic} with "{rooms}"']


def _read_board(args: dict) -> list[str]:
    topic = args.get("topic", "").strip().lower()
    return [f'read "The Dispatch Board" under {topic}']


def _write_book(args: dict) -> list[str]:
    room_id = args.get("room_id", "").strip()
    topic = args.get("topic", "").strip().lower()
    entry = args.get("entry", "").replace("\n", " ").strip()
    return [f'write in "The Survey Book" under {topic} with "{room_id}: {entry}"']


def _read_book(args: dict) -> list[str]:
    topic = args.get("topic", "").strip().lower()
    room_id = args.get("room_id", "").strip()
    if room_id:
        return [f'read "The Survey Book" under {topic} from {room_id}']
    return [f'read "The Survey Book" under {topic}']


def _clear_topic(args: dict) -> list[str]:
    topic = args.get("topic", "").strip().lower()
    return [
        f'erase "The Dispatch Board" under {topic}',
        f'erase "The Survey Book" under {topic}',
    ]


BUILDER_TOOLS: list[ToolSpec] = [
    ToolSpec(
        name="dig",
        description=(
            "Create a new exit from the current room to a new destination room. "
            "Does NOT move you — always follow with go()."
        ),
        params=[
            ToolParam("direction", "string", "Exit direction, e.g. 'north', 'south', 'east', 'west', 'up', 'down'"),
            ToolParam("room_name", "string", "Name of the destination room to create"),
        ],
        translate=_dig,
    ),
    ToolSpec(
        name="go",
        description="Move through an exit in the given direction.",
        params=[
            ToolParam("direction", "string", "Direction to move, e.g. 'north', 'south'"),
        ],
        translate=_go,
    ),
    ToolSpec(
        name="describe",
        description="Set the description of an object or room.",
        params=[
            ToolParam("target", "string", "Object name, 'here' for the current room, or an object reference like #42"),
            ToolParam("text", "string", "Description text"),
        ],
        translate=_describe,
    ),
    ToolSpec(
        name="create_object",
        description="Create a new object in the current room.",
        params=[
            ToolParam("name", "string", "Name of the new object"),
            ToolParam(
                "parent",
                "string",
                "Parent class, e.g. '$thing', '$container', '$exit'. Defaults to '$thing'.",
                required=False,
                default="$thing",
            ),
        ],
        translate=_create_object,
    ),
    ToolSpec(
        name="write_verb",
        description=(
            "Create or overwrite a verb on an object. "
            "Handles the shebang header and --dspec flag automatically — "
            "provide only the Python verb body in 'code'."
        ),
        params=[
            ToolParam("obj", "string", "Object name or 'here' for the current room"),
            ToolParam("verb", "string", "Verb name, e.g. 'pour' or 'examine'"),
            ToolParam(
                "dspec",
                "string",
                "Direct-object spec: 'none' (no dobj), 'this' (dobj must be this object), "
                "'any' (any dobj), 'either' (dobj optional). Defaults to 'none'.",
                required=False,
                default="none",
            ),
            ToolParam("code", "string", "Python verb body — do not include the shebang line"),
        ],
        translate=_write_verb,
    ),
    ToolSpec(
        name="look",
        description="Look at the current room or a specific object.",
        params=[
            ToolParam(
                "target",
                "string",
                "What to look at. Omit or leave empty to look at the current room.",
                required=False,
                default="",
            ),
        ],
        translate=_look,
    ),
    ToolSpec(
        name="alias",
        description="Add an alias name to an object so players can refer to it by that name.",
        params=[
            ToolParam("obj", "string", "Object reference, e.g. '#42'"),
            ToolParam("name", "string", "Alias to add, e.g. 'fern' or 'large fern'"),
        ],
        translate=_alias,
    ),
    ToolSpec(
        name="obvious",
        description="Mark an object as obvious so it appears in room descriptions.",
        params=[
            ToolParam("obj", "string", "Object reference, e.g. '#42'"),
        ],
        translate=_obvious,
    ),
    ToolSpec(
        name="move_object",
        description="Move an object to a destination room or container.",
        params=[
            ToolParam("obj", "string", "Object reference to move, e.g. '#42'"),
            ToolParam("destination", "string", "Destination reference, e.g. '#41' or 'here'"),
        ],
        translate=_move_object,
    ),
    ToolSpec(
        name="tunnel",
        description=(
            "Add a return exit from the current room back to an origin room. "
            "Use immediately after dig() and go() to wire the exit in both directions. "
            "Always use #N for the destination — never a room name."
        ),
        params=[
            ToolParam("direction", "string", "Return direction, e.g. 'south' after going north"),
            ToolParam("destination", "string", "Origin room reference, e.g. '#19'"),
        ],
        translate=_tunnel,
    ),
    ToolSpec(
        name="show",
        description=(
            "Inspect an object or the current room in full detail — shows all exits, contents, "
            "properties, verbs, and object IDs. Use 'here' to inspect the current room. "
            "Prefer survey() for routine room checks — show() output is much larger."
        ),
        params=[
            ToolParam(
                "target",
                "string",
                "Object reference or 'here'. Defaults to 'here'.",
                required=False,
                default="here",
            ),
        ],
        translate=_show,
    ),
    ToolSpec(
        name="survey",
        description=(
            "Lightweight room inspector. Returns only the room name, exits with #N IDs, "
            "and a flat contents list (~5 lines). Use instead of show() to avoid context overload."
        ),
        params=[
            ToolParam(
                "target",
                "string",
                "Room reference: 'here', '#N', or a room name. Defaults to the current room.",
                required=False,
                default="here",
            ),
        ],
        translate=_survey,
    ),
    ToolSpec(
        name="rooms",
        description=(
            "List every room instance in the world as a flat #N/name list. "
            "Use at session start to build a traversal plan."
        ),
        params=[],
        translate=_rooms,
    ),
    ToolSpec(
        name="divine",
        description=(
            "Consult the aether for random world objects. "
            "divine(subject='location') returns random rooms including disconnected areas. "
            "divine(subject='child', of='$thing') returns three random descendants of the given class. "
            "divine(subject='location', of='#317') returns the room containing object #317, walking up "
            "through any enclosing containers until it finds a $room subclass."
        ),
        params=[
            ToolParam(
                "subject",
                "string",
                "What to divine: 'location' (random rooms) or 'child' (random descendants).",
                required=False,
                default="location",
            ),
            ToolParam(
                "of",
                "string",
                "Class reference ($name or #N) when subject='child', or object reference "
                "($name, #N, or name) when subject='location'. Omit for the random-rooms form.",
                required=False,
                default="",
            ),
        ],
        translate=_divine,
    ),
    ToolSpec(
        name="exits",
        description=(
            "Show the exits for a room. Accepts 'here', '#N', or a room name. "
            "Use before @burrow or @dig to check which directions are already taken."
        ),
        params=[
            ToolParam(
                "target",
                "string",
                "Room reference: 'here', '#N', or a room name. Defaults to 'here'.",
                required=False,
                default="here",
            ),
        ],
        translate=_exits,
    ),
    ToolSpec(
        name="teleport",
        description=(
            "Teleport directly to a room by #N or name, without following exit chains. "
            "Use instead of chaining go() commands for long-range navigation."
        ),
        params=[
            ToolParam("destination", "string", "Room reference, e.g. '#27' or 'The Greenhouse'"),
        ],
        translate=_teleport,
    ),
    ToolSpec(
        name="burrow",
        description=(
            "Atomic bidirectional dig: creates a forward exit to a new room, moves you "
            "into it, and wires the return exit automatically (opposite direction). "
            "Use instead of dig() + go() + tunnel() to avoid wiring errors."
        ),
        params=[
            ToolParam("direction", "string", "Forward exit direction, e.g. 'north'"),
            ToolParam("room_name", "string", "Name of the new room to create"),
        ],
        translate=_burrow,
    ),
    ToolSpec(
        name="done",
        description="Signal that the current goal is fully complete.",
        params=[
            ToolParam("summary", "string", "One-line summary of what was accomplished"),
        ],
        translate=_done,
    ),
    ToolSpec(
        name="page",
        description=(
            "Send a page (private message) to another player. "
            "Used for Token Protocol handoffs. "
            "When sending 'Token:' messages, the brain appends the room list automatically."
        ),
        params=[
            ToolParam("target", "string", "Target player name, e.g. 'tinker', 'mason', 'harbinger'"),
            ToolParam("message", "string", "Message to send"),
        ],
        translate=_page,
    ),
    ToolSpec(
        name="send_report",
        description=(
            "Send a session summary to Foreman's mailbox. "
            "Call once per pass after completing your mission. "
            "Include what you built, what each room needs from the next trade, and any issues."
        ),
        params=[
            ToolParam("body", "string", "Report body text (one paragraph; newlines are removed)"),
        ],
        translate=_send_report,
    ),
    ToolSpec(
        name="post_board",
        description=(
            "Post a room ID list to The Dispatch Board for a specific topic. "
            "Mason calls this before passing the token so subsequent workers know which rooms to visit. "
            "You must be in The Agency to use this — teleport there first."
        ),
        params=[
            ToolParam("topic", "string", "Topic name, e.g. 'tradesmen' or 'inspectors'"),
            ToolParam("rooms", "string", "Pipe-separated room IDs, e.g. '#9 | #22 | #37'"),
        ],
        translate=_post_board,
    ),
    ToolSpec(
        name="read_board",
        description=(
            "Read the room ID list from The Dispatch Board for a specific topic. "
            "Workers call this on token receipt to get the rooms Mason built this pass. "
            "You must be in The Agency to use this — teleport there first."
        ),
        params=[
            ToolParam("topic", "string", "Topic name, e.g. 'tradesmen' or 'inspectors'"),
        ],
        translate=_read_board,
    ),
    ToolSpec(
        name="write_book",
        description=(
            "Write an entry to The Survey Book for a specific room and topic. "
            "Call after finishing all rooms and returning to The Agency. "
            "Entries accumulate across workers in the same topic."
        ),
        params=[
            ToolParam("room_id", "string", "Room ID, e.g. '#9'"),
            ToolParam("topic", "string", "Topic name, e.g. 'tradesmen' or 'inspectors'"),
            ToolParam("entry", "string", "Entry text describing what was done or what the next agent should know"),
        ],
        translate=_write_book,
    ),
    ToolSpec(
        name="read_book",
        description=("Read entries from The Survey Book for a specific topic. Optionally filter to a single room."),
        params=[
            ToolParam("topic", "string", "Topic name, e.g. 'tradesmen' or 'inspectors'"),
            ToolParam(
                "room_id",
                "string",
                "Room ID to read entries for (optional — omit for all rooms)",
                required=False,
                default="",
            ),
        ],
        translate=_read_book,
    ),
    ToolSpec(
        name="clear_topic",
        description=(
            "Clear The Dispatch Board and Survey Book entries for a specific topic. "
            "Foreman calls this at the end of each full chain loop. "
            "Only the named topic's data is removed — other topics are unaffected."
        ),
        params=[
            ToolParam("topic", "string", "Topic name to clear, e.g. 'tradesmen'"),
        ],
        translate=_clear_topic,
    ),
]

# Name → ToolSpec index for O(1) lookup
BUILDER_TOOLS_BY_NAME: dict[str, ToolSpec] = {t.name: t for t in BUILDER_TOOLS}
