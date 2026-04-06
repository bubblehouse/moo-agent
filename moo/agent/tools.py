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
    """Replace <|"|>value<|"|> token wrappers with plain "value"."""
    return _GEMMA_STR_TOKEN_RE.sub(r'"\1"', s)


def parse_tool_line(line: str, known_names: "set[str] | None" = None) -> tuple[str, dict] | None:
    """
    Parse a tool-call directive from an LM Studio response line.

    Returns (tool_name, args_dict) or None if the line doesn't match.

    Supported formats:
      TOOL: dig(direction="north" room_name="The Library")
      call:dig{direction: "north", room_name: "The Library"}
      tool_call:dig{direction: <|"|>north<|"|>, room_name: <|"|>The Library<|"|>}
      move_object(obj="#44", destination="#41")  — bare call, validated against known_names
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
    direction = args["direction"].strip().lower().lstrip("#")
    # Reject room IDs passed as directions (e.g. "#41" or "41")
    if direction.isdigit() or direction not in _VALID_DIRECTIONS:
        return [
            f'say ERROR: go() requires a compass direction (north/south/east/west/up/down), not "{args["direction"].strip()}"'
        ]
    return [f"go {direction}"]


def _describe(args: dict) -> list[str]:
    target = args["target"].strip()
    text = args["text"].strip().strip('"')
    return [f'@describe {target} as "{text}"']


def _create_object(args: dict) -> list[str]:
    name = args["name"].strip().strip('"')
    parent = args.get("parent", "$thing").strip().strip('"') or "$thing"
    return [f'@create "{name}" from "{parent}"']


def _write_verb(args: dict) -> list[str]:
    obj = args["obj"].strip()
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
    obj = args["obj"].strip()
    prop = args["prop"].strip()
    value = args["value"].strip()
    return [f"@set {obj}.{prop} to {value}"]


def _look(args: dict) -> list[str]:
    target = (args.get("target") or "").strip()
    return [f"look {target}".rstrip()] if target else ["look"]


def _alias(args: dict) -> list[str]:
    obj = args["obj"].strip()
    name = args["name"].strip().strip('"')
    return [f'@alias {obj} as "{name}"']


def _make_obvious(args: dict) -> list[str]:
    obj = args["obj"].strip()
    return [f"@obvious {obj}"]


def _move_object(args: dict) -> list[str]:
    obj = args["obj"].strip()
    destination = args["destination"].strip()
    return [f"@move {obj} to {destination}"]


def _show(args: dict) -> list[str]:
    target = (args.get("target") or "here").strip()
    return [f"@show {target}"]


def _tunnel(args: dict) -> list[str]:
    direction = args["direction"].strip()
    destination = args["destination"].strip()
    return [f"@tunnel {direction} to {destination}"]


def _done(_args: dict) -> list[str]:
    # Brain intercepts the 'done' tool call to update goal state; no MOO command.
    return []


def _page(args: dict) -> list[str]:
    target = args["target"].strip()
    message = args.get("message", "").replace("\n", " ").strip()
    # Brain intercepts 'page' calls that carry "Token:" to inject the room list.
    return [f"page {target} with {message}"]


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
        name="make_obvious",
        description="Mark an object as obvious so it appears in room descriptions.",
        params=[
            ToolParam("obj", "string", "Object reference, e.g. '#42'"),
        ],
        translate=_make_obvious,
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
            "Inspect an object or the current room in detail — shows exits, contents, "
            "properties, and object IDs. Use 'here' to inspect the current room."
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
]

# Name → ToolSpec index for O(1) lookup
BUILDER_TOOLS_BY_NAME: dict[str, ToolSpec] = {t.name: t for t in BUILDER_TOOLS}
