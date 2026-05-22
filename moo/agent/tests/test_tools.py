"""
Tests for moo/agent/tools.py.

Covers ToolSpec schema generation, translate() output for each BUILDER_TOOL,
the synthetic raw/respond tools, and get_tool() lookup.
Does not require DJANGO_SETTINGS_MODULE.
"""

import pytest

from moo.agent.tools import (
    BUILDER_TOOLS,
    BUILDER_TOOLS_BY_NAME,
    SYSTEM_TOOLS,
    get_tool,
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


def test_look_translate_rejects_verb_test_pattern():
    spec = BUILDER_TOOLS_BY_NAME["look"]
    with pytest.raises(ValueError, match="not how you test a verb"):
        spec.translate({"target": "peer #1152"})
    with pytest.raises(ValueError, match="not how you test a verb"):
        spec.translate({"target": "crank #1151"})


def test_look_translate_allows_id_only_target():
    spec = BUILDER_TOOLS_BY_NAME["look"]
    assert spec.translate({"target": "#1152"}) == ["look #1152"]


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


def test_builder_tools_by_name_covers_builder_and_system_tools():
    assert set(BUILDER_TOOLS_BY_NAME.keys()) == {t.name for t in BUILDER_TOOLS + SYSTEM_TOOLS}


# ---------------------------------------------------------------------------
# Synthetic system tools — raw and respond
# ---------------------------------------------------------------------------


def test_raw_translate_passes_command_verbatim():
    spec = BUILDER_TOOLS_BY_NAME["raw"]
    assert spec.translate({"command": "@realm $room"}) == ["@realm $room"]


def test_raw_translate_empty_command_is_noop():
    spec = BUILDER_TOOLS_BY_NAME["raw"]
    assert spec.translate({"command": "  "}) == []
    assert spec.translate({}) == []


def test_respond_translate_returns_no_commands():
    spec = BUILDER_TOOLS_BY_NAME["respond"]
    assert spec.translate({"message": "just thinking"}) == []
