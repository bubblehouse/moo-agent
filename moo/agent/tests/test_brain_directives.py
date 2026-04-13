"""
Table-driven tests for moo/agent/brain_directives.py.

parse_llm_response is a pure function: given an LLM response body it returns
an ordered list of Directives plus thought_lines. These tests cover the
directive grammar exhaustively — including the quirky edge cases preserved
from the in-Brain implementation (markdown bold strip, XML unwrap,
COMMAND: SCRIPT: nesting, BUILD_PLAN flush).
"""

from moo.agent.brain.directives import (
    Directive,
    parse_llm_response,
    extract_room_names_from_yaml,
)


def _kinds(directives: list[Directive]) -> list[str]:
    return [d.kind for d in directives]


def test_plain_goal():
    r = parse_llm_response("GOAL: build the library")
    assert r.directives == [Directive("goal", "build the library")]
    assert not r.thought_lines


def test_plain_command():
    r = parse_llm_response("COMMAND: look")
    assert r.directives == [Directive("command", "look")]


def test_plain_done():
    r = parse_llm_response("DONE: all rooms built")
    assert r.directives == [Directive("done", "all rooms built")]


def test_plain_script():
    r = parse_llm_response("SCRIPT: look | go north | look")
    # Script directives preserve the whole line so _handle_script_line can parse it.
    assert r.directives == [Directive("script", "SCRIPT: look | go north | look")]


def test_plan_directive():
    r = parse_llm_response("PLAN: step one | step two | step three")
    assert r.directives == [Directive("plan", "step one | step two | step three")]


def test_markdown_bold_stripped():
    r = parse_llm_response("**COMMAND:** look")
    assert r.directives == [Directive("command", "look")]


def test_markdown_bold_with_extra_asterisks():
    r = parse_llm_response("***COMMAND:*** look")
    assert r.directives == [Directive("command", "look")]


def test_xml_action_wrapper_stripped():
    r = parse_llm_response("<action>COMMAND: look</action>")
    assert r.directives == [Directive("command", "look")]


def test_xml_tool_wrapper_stripped():
    r = parse_llm_response("<tool>GOAL: find the exit</tool>")
    assert r.directives == [Directive("goal", "find the exit")]


def test_command_backticks_stripped():
    r = parse_llm_response("COMMAND: `@dig north to nowhere`")
    assert r.directives == [Directive("command", "@dig north to nowhere")]


def test_nested_command_script_promoted():
    """COMMAND: SCRIPT: a | b promotes the SCRIPT: to a script directive.

    Also emits an empty command directive so any earlier COMMAND: in the
    same response is overwritten — matches the original in-loop semantics
    where `command_line = ""` was reassigned after the nested script ran.
    """
    r = parse_llm_response("COMMAND: SCRIPT: look | go north")
    assert r.directives == [
        Directive("script", "SCRIPT: look | go north"),
        Directive("command", ""),
    ]


def test_nested_command_script_overwrites_prior_command():
    r = parse_llm_response("COMMAND: look\nCOMMAND: SCRIPT: a | b")
    kinds = _kinds(r.directives)
    # First COMMAND: survives, then the nested-script case adds script + empty command.
    assert kinds == ["command", "script", "command"]
    assert r.directives[0].value == "look"
    assert r.directives[1].value == "SCRIPT: a | b"
    assert r.directives[2].value == ""


def test_patch_rule():
    r = parse_llm_response("SOUL_PATCH_RULE: (?i)huh\\? -> help me")
    assert r.directives == [Directive("patch_rule", "(?i)huh\\? -> help me")]


def test_patch_verb():
    r = parse_llm_response("SOUL_PATCH_VERB: pick up -> take")
    assert r.directives == [Directive("patch_verb", "pick up -> take")]


def test_patch_note():
    r = parse_llm_response("SOUL_PATCH_NOTE: dig south, not @dig south")
    assert r.directives == [Directive("patch_note", "dig south, not @dig south")]


def test_build_plan_single_line():
    r = parse_llm_response("BUILD_PLAN: rooms:\n  - name: Foyer")
    # BUILD_PLAN accumulates lines after it until the next directive or end.
    assert len(r.directives) == 1
    d = r.directives[0]
    assert d.kind == "build_plan"
    assert "rooms:" in d.value
    assert "- name: Foyer" in d.value


def test_build_plan_multi_line_ended_by_directive():
    text = "BUILD_PLAN: rooms:\n  - name: Foyer\n    exits:\n      - north: Hall\nCOMMAND: look"
    r = parse_llm_response(text)
    kinds = _kinds(r.directives)
    assert kinds == ["build_plan", "command"]
    assert "Foyer" in r.directives[0].value
    assert "north: Hall" in r.directives[0].value
    assert r.directives[1].value == "look"


def test_build_plan_flushes_at_end_of_response():
    text = "BUILD_PLAN: rooms:\n  - name: Foyer\n  - name: Hall"
    r = parse_llm_response(text)
    assert len(r.directives) == 1
    assert r.directives[0].kind == "build_plan"
    assert "Foyer" in r.directives[0].value
    assert "Hall" in r.directives[0].value


def test_build_plan_bare_header_requires_content():
    """A bare `BUILD_PLAN:` line with no trailing content does not match
    the regex (`.+` requires at least one char). The original in-Brain
    implementation had the same behavior."""
    text = "BUILD_PLAN:\n  - name: Foyer"
    r = parse_llm_response(text)
    assert not r.directives
    # Both lines fall through to thought_lines.
    assert any("Foyer" in line for line in r.thought_lines)


def test_thought_lines_collected():
    text = "I should probably look around first.\nCOMMAND: look"
    r = parse_llm_response(text)
    assert r.directives == [Directive("command", "look")]
    assert "I should probably look around first." in r.thought_lines


def test_multiple_directives_preserve_order():
    text = "GOAL: explore\nPLAN: look | north | south\nCOMMAND: look"
    r = parse_llm_response(text)
    kinds = _kinds(r.directives)
    assert kinds == ["goal", "plan", "command"]


def test_empty_response():
    r = parse_llm_response("")
    assert not r.directives
    assert not r.thought_lines


def test_only_thought_lines():
    r = parse_llm_response("just some musing\nnothing to do")
    assert not r.directives
    assert len(r.thought_lines) == 2


def test_extract_room_names_from_yaml():
    text = (
        "rooms:\n"
        "  - name: Foyer\n"
        "    desc: Entrance hall\n"
        "  - name: Great Hall\n"
        "  - name: 'Kitchen'\n"
        '  - name: "Library"\n'
    )
    names = extract_room_names_from_yaml(text)
    assert names == ["Foyer", "Great Hall", "Kitchen", "Library"]


def test_extract_room_names_empty():
    assert extract_room_names_from_yaml("") == []
    assert extract_room_names_from_yaml("no rooms here") == []


def test_goal_strips_whitespace():
    r = parse_llm_response("GOAL:    build the library   ")
    assert r.directives[0].value == "build the library"


def test_done_strips_whitespace():
    r = parse_llm_response("DONE:   all done  ")
    assert r.directives[0].value == "all done"


def test_plan_payload_raw():
    # PLAN: payload is returned with leading whitespace already consumed by
    # the `\s*` in the regex; the consumer splits on "|" and strips each piece.
    r = parse_llm_response("PLAN: a | b | c")
    assert r.directives[0].value == "a | b | c"
