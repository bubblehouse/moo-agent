"""
Tests for moo/agent/tools.py.

Covers ToolSpec schema generation, translate() output for each BUILDER_TOOL,
parse_tool_line() for the LM Studio string fallback, and get_tool() lookup.
Does not require DJANGO_SETTINGS_MODULE.
"""

import pytest

from moo.agent.tools import (
    BUILDER_TOOLS,
    BUILDER_TOOLS_BY_NAME,
    LLMResponse,
    ToolParam,
    ToolSpec,
    get_tool,
    parse_tool_line,
)


# ---------------------------------------------------------------------------
# ToolSpec schema generation
# ---------------------------------------------------------------------------


def test_to_anthropic_schema_shape():
    spec = BUILDER_TOOLS_BY_NAME["dig"]
    schema = spec.to_anthropic_schema()
    assert schema["name"] == "dig"
    assert "description" in schema
    assert schema["input_schema"]["type"] == "object"
    assert "direction" in schema["input_schema"]["properties"]
    assert "room_name" in schema["input_schema"]["properties"]
    assert "direction" in schema["input_schema"]["required"]
    assert "room_name" in schema["input_schema"]["required"]


def test_to_openai_schema_shape():
    spec = BUILDER_TOOLS_BY_NAME["go"]
    schema = spec.to_openai_schema()
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "go"
    assert "direction" in schema["function"]["parameters"]["properties"]
    assert "direction" in schema["function"]["parameters"]["required"]


def test_optional_param_not_in_required():
    spec = BUILDER_TOOLS_BY_NAME["create_object"]
    schema = spec.to_anthropic_schema()
    assert "name" in schema["input_schema"]["required"]
    assert "parent" not in schema["input_schema"]["required"]


def test_optional_param_has_default_in_schema():
    spec = BUILDER_TOOLS_BY_NAME["create_object"]
    schema = spec.to_anthropic_schema()
    assert schema["input_schema"]["properties"]["parent"]["default"] == "$thing"


# ---------------------------------------------------------------------------
# translate() — each BUILDER_TOOL
# ---------------------------------------------------------------------------


def test_dig_translate():
    spec = BUILDER_TOOLS_BY_NAME["dig"]
    cmds = spec.translate({"direction": "north", "room_name": "The Library"})
    assert cmds == ['@dig north to "The Library"']


def test_dig_translate_strips_quotes_from_room_name():
    spec = BUILDER_TOOLS_BY_NAME["dig"]
    cmds = spec.translate({"direction": "east", "room_name": '"The Vault"'})
    assert cmds == ['@dig east to "The Vault"']


def test_go_translate():
    spec = BUILDER_TOOLS_BY_NAME["go"]
    cmds = spec.translate({"direction": "south"})
    assert cmds == ["go south"]


def test_describe_translate():
    spec = BUILDER_TOOLS_BY_NAME["describe"]
    cmds = spec.translate({"target": "here", "text": "A dimly lit corridor."})
    assert cmds == ['@describe here as "A dimly lit corridor."']


def test_describe_translate_strips_quotes_from_text():
    spec = BUILDER_TOOLS_BY_NAME["describe"]
    cmds = spec.translate({"target": "here", "text": '"Quoted text."'})
    assert cmds == ['@describe here as "Quoted text."']


def test_create_object_translate_with_default_parent():
    spec = BUILDER_TOOLS_BY_NAME["create_object"]
    cmds = spec.translate({"name": "brass lamp"})
    assert cmds == ['@create "brass lamp" from "$thing" in here']


def test_create_object_translate_custom_parent():
    spec = BUILDER_TOOLS_BY_NAME["create_object"]
    cmds = spec.translate({"name": "chest", "parent": "$container"})
    assert cmds == ['@create "chest" from "$container" in here']


def test_write_verb_translate_includes_shebang():
    spec = BUILDER_TOOLS_BY_NAME["write_verb"]
    cmds = spec.translate({"obj": "here", "verb": "pour", "code": "print('poured')"})
    assert len(cmds) == 1
    cmd = cmds[0]
    assert cmd.startswith("@edit verb pour on here with ")
    # Shebang must be on the first line with --on and --dspec flags
    assert "#!moo verb pour --on $thing --dspec none" in cmd
    assert "print('poured')" in cmd


def test_write_verb_translate_custom_dspec():
    spec = BUILDER_TOOLS_BY_NAME["write_verb"]
    cmds = spec.translate({"obj": "here", "verb": "examine", "dspec": "any", "code": "print('look')"})
    cmd = cmds[0]
    assert "--dspec any" in cmd


def test_write_verb_translate_shebang_single_line():
    """parse_shebang reads only the first line; all flags must be on it."""
    import json

    spec = BUILDER_TOOLS_BY_NAME["write_verb"]
    cmds = spec.translate({"obj": "here", "verb": "test", "code": "pass"})
    cmd = cmds[0]
    parts = cmd.split(" with ", 1)
    assert len(parts) == 2
    source = json.loads(parts[1])
    lines = source.splitlines()
    # First line must contain the full shebang with --on and --dspec
    assert lines[0].startswith("#!moo verb test")
    assert "--on $thing" in lines[0]
    assert "--dspec" in lines[0]
    # Code starts on line 2
    assert lines[1] == "pass"


def test_look_translate_no_target():
    spec = BUILDER_TOOLS_BY_NAME["look"]
    assert spec.translate({}) == ["look"]
    assert spec.translate({"target": ""}) == ["look"]


def test_look_translate_with_target():
    spec = BUILDER_TOOLS_BY_NAME["look"]
    cmds = spec.translate({"target": "brass lamp"})
    assert cmds == ["look brass lamp"]


def test_done_translate_returns_no_commands():
    spec = BUILDER_TOOLS_BY_NAME["done"]
    cmds = spec.translate({"summary": "All rooms built."})
    assert cmds == []


def test_alias_translate():
    spec = BUILDER_TOOLS_BY_NAME["alias"]
    cmds = spec.translate({"obj": "#39", "name": "fern"})
    assert cmds == ['@alias #39 as "fern"']


def test_alias_translate_strips_quotes():
    spec = BUILDER_TOOLS_BY_NAME["alias"]
    cmds = spec.translate({"obj": "#39", "name": '"large fern"'})
    assert cmds == ['@alias #39 as "large fern"']


def test_obvious_translate():
    spec = BUILDER_TOOLS_BY_NAME["obvious"]
    cmds = spec.translate({"obj": "#42"})
    assert cmds == ["@obvious #42"]


def test_move_object_translate():
    spec = BUILDER_TOOLS_BY_NAME["move_object"]
    cmds = spec.translate({"obj": "#42", "destination": "#41"})
    assert cmds == ["@move #42 to #41"]


def test_show_translate_default():
    spec = BUILDER_TOOLS_BY_NAME["show"]
    cmds = spec.translate({})
    assert cmds == ["@show here"]


def test_show_translate_with_target():
    spec = BUILDER_TOOLS_BY_NAME["show"]
    cmds = spec.translate({"target": "#42"})
    assert cmds == ["@show #42"]


# ---------------------------------------------------------------------------
# get_tool()
# ---------------------------------------------------------------------------


def test_get_tool_found():
    spec = get_tool(BUILDER_TOOLS, "dig")
    assert spec is not None
    assert spec.name == "dig"


def test_get_tool_not_found():
    assert get_tool(BUILDER_TOOLS, "nonexistent") is None


def test_builder_tools_by_name_covers_all():
    assert set(BUILDER_TOOLS_BY_NAME.keys()) == {t.name for t in BUILDER_TOOLS}


# ---------------------------------------------------------------------------
# parse_tool_line() — LM Studio string fallback
# ---------------------------------------------------------------------------


def test_parse_tool_line_simple():
    result = parse_tool_line('TOOL: dig(direction="north" room_name="The Library")')
    assert result is not None
    name, args = result
    assert name == "dig"
    assert args["direction"] == "north"
    assert args["room_name"] == "The Library"


def test_parse_tool_line_single_arg():
    result = parse_tool_line('TOOL: go(direction="south")')
    assert result is not None
    name, args = result
    assert name == "go"
    assert args["direction"] == "south"


def test_parse_tool_line_single_quoted_value():
    result = parse_tool_line("TOOL: look(target='brass lamp')")
    assert result is not None
    _, args = result
    assert args["target"] == "brass lamp"


def test_parse_tool_line_no_match_on_plain_text():
    assert parse_tool_line("COMMAND: go north") is None
    assert parse_tool_line("GOAL: explore") is None
    assert parse_tool_line("") is None


def test_parse_tool_line_no_match_on_missing_parens():
    assert parse_tool_line("TOOL: dig direction=north") is None


def test_parse_tool_line_strips_leading_whitespace():
    result = parse_tool_line('  TOOL: go(direction="north")')
    assert result is not None
    assert result[0] == "go"


# ---------------------------------------------------------------------------
# Gemma 4 native call: format
# ---------------------------------------------------------------------------


def test_parse_tool_line_gemma_call_prefix():
    result = parse_tool_line('call:dig{direction: "north", room_name: "The Library"}')
    assert result is not None
    name, args = result
    assert name == "dig"
    assert args["direction"] == "north"
    assert args["room_name"] == "The Library"


def test_parse_tool_line_gemma_tool_call_prefix():
    result = parse_tool_line('tool_call:go{direction: "south"}')
    assert result is not None
    name, args = result
    assert name == "go"
    assert args["direction"] == "south"


def test_parse_tool_line_gemma_special_tokens():
    """Gemma wraps string values in pipe-delimited chat tokens; strips them cleanly."""
    result = parse_tool_line('tool_call:go{direction:<|"|>east<|"|>}')
    assert result is not None
    name, args = result
    assert name == "go"
    assert args["direction"] == "east"


def test_parse_tool_line_gemma_special_tokens_multiarg():
    result = parse_tool_line('tool_call:dig{direction:<|"|>north<|"|>, room_name:<|"|>The Library<|"|>}')
    assert result is not None
    name, args = result
    assert name == "dig"
    assert args["direction"] == "north"
    assert args["room_name"] == "The Library"


def test_parse_tool_line_gemma_no_quotes():
    result = parse_tool_line("call:go{direction: north}")
    assert result is not None
    _, args = result
    assert args["direction"] == "north"


def test_parse_tool_line_gemma_create_object():
    result = parse_tool_line('call:create_object{name: "pulsing fern", parent: "$thing"}')
    assert result is not None
    name, args = result
    assert name == "create_object"
    assert args["name"] == "pulsing fern"
    assert args["parent"] == "$thing"


def test_parse_tool_line_gemma_no_match_on_plain_text():
    assert parse_tool_line("call:") is None
    assert parse_tool_line("call:foo") is None  # no braces
    assert parse_tool_line("tool_call:") is None


# ---------------------------------------------------------------------------
# LLMResponse dataclass
# ---------------------------------------------------------------------------


def test_llm_response_defaults():
    r = LLMResponse(text="hello")
    assert r.text == "hello"
    assert not r.tool_calls


def test_llm_response_with_tool_calls():
    r = LLMResponse(text="", tool_calls=[("dig", {"direction": "north", "room_name": "X"})])
    assert len(r.tool_calls) == 1
    assert r.tool_calls[0][0] == "dig"
