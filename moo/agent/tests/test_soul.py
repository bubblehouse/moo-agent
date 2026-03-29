"""
Tests for moo/agent/soul.py.

These tests do not require DJANGO_SETTINGS_MODULE and do not import from moo.core.
"""

import re

import pytest

from moo.agent.soul import Rule, VerbMapping, append_patch, compile_rules, parse_soul

FULL_SOUL_MD = """\
# Name
Jeeves

# Mission
You are Jeeves, a butler in a text-based MOO world.

# Persona
Speak in formal British English. Address players as "sir" or "madam."

## Rules of Engagement
- `^You feel hungry` -> eat crumpets
- `(?i)ring.*bell` -> say How may I assist you?

## Verb Mapping
- look_around -> look
- greet_player -> say Good evening!
"""


def _write_soul(tmp_path, content, filename="SOUL.md"):
    p = tmp_path / filename
    p.write_text(content)
    return tmp_path


def test_parse_name(tmp_path):
    _write_soul(tmp_path, FULL_SOUL_MD)
    soul = parse_soul(tmp_path)
    assert soul.name == "Jeeves"


def test_parse_mission(tmp_path):
    _write_soul(tmp_path, FULL_SOUL_MD)
    soul = parse_soul(tmp_path)
    assert "butler" in soul.mission


def test_parse_persona(tmp_path):
    _write_soul(tmp_path, FULL_SOUL_MD)
    soul = parse_soul(tmp_path)
    assert "formal British English" in soul.persona


def test_parse_rules(tmp_path):
    _write_soul(tmp_path, FULL_SOUL_MD)
    soul = parse_soul(tmp_path)
    assert len(soul.rules) == 2
    assert soul.rules[0].pattern == "^You feel hungry"
    assert soul.rules[0].command == "eat crumpets"
    assert soul.rules[1].pattern == "(?i)ring.*bell"


def test_parse_verb_mappings(tmp_path):
    _write_soul(tmp_path, FULL_SOUL_MD)
    soul = parse_soul(tmp_path)
    assert len(soul.verb_mappings) == 2
    assert soul.verb_mappings[0].intent == "look_around"
    assert soul.verb_mappings[0].template == "look"
    assert soul.verb_mappings[1].intent == "greet_player"


def test_unicode_arrow_separator(tmp_path):
    content = "# Name\nTest\n# Mission\nM\n# Persona\nP\n## Rules of Engagement\n- trigger → do something\n"
    _write_soul(tmp_path, content)
    soul = parse_soul(tmp_path)
    assert len(soul.rules) == 1
    assert soul.rules[0].pattern == "trigger"
    assert soul.rules[0].command == "do something"


def test_missing_rules_section_returns_empty(tmp_path):
    content = "# Name\nTest\n# Mission\nM\n# Persona\nP\n"
    _write_soul(tmp_path, content)
    soul = parse_soul(tmp_path)
    assert not soul.rules
    assert not soul.verb_mappings


def test_missing_name_returns_empty_string(tmp_path):
    content = "# Mission\nM\n# Persona\nP\n"
    _write_soul(tmp_path, content)
    soul = parse_soul(tmp_path)
    assert soul.name == ""


def test_compile_rules_returns_patterns(tmp_path):
    _write_soul(tmp_path, FULL_SOUL_MD)
    soul = parse_soul(tmp_path)
    compiled = compile_rules(soul)
    assert len(compiled) == 2
    assert all(isinstance(p, re.Pattern) for p, _ in compiled)


def test_compile_rules_empty_list():
    from moo.agent.soul import Soul

    soul = Soul()
    compiled = compile_rules(soul)
    assert compiled == []


def test_patch_rules_appended_after_base(tmp_path):
    _write_soul(tmp_path, FULL_SOUL_MD)
    patch_content = "## Rules of Engagement\n- ^base wins -> base\n"
    _write_soul(tmp_path, patch_content, filename="SOUL.patch.md")
    soul = parse_soul(tmp_path)
    # Base rules come first
    assert soul.rules[0].pattern == "^You feel hungry"
    assert soul.rules[-1].pattern == "^base wins"


def test_append_patch_creates_file(tmp_path):
    _write_soul(tmp_path, FULL_SOUL_MD)
    append_patch(tmp_path, "rule", "^You are thirsty", "drink water")
    patch_path = tmp_path / "SOUL.patch.md"
    assert patch_path.exists()
    text = patch_path.read_text()
    assert "^You are thirsty -> drink water" in text
    assert "## Rules of Engagement" in text


def test_append_patch_no_duplicate(tmp_path):
    _write_soul(tmp_path, FULL_SOUL_MD)
    append_patch(tmp_path, "rule", "^You are thirsty", "drink water")
    append_patch(tmp_path, "rule", "^You are thirsty", "drink water")
    patch_path = tmp_path / "SOUL.patch.md"
    count = patch_path.read_text().count("^You are thirsty -> drink water")
    assert count == 1


def test_append_patch_verb_section(tmp_path):
    _write_soul(tmp_path, FULL_SOUL_MD)
    append_patch(tmp_path, "verb", "go_east", "go east")
    text = (tmp_path / "SOUL.patch.md").read_text()
    assert "## Verb Mapping" in text
    assert "go_east -> go east" in text


def test_parse_soul_merges_patch_verbs(tmp_path):
    _write_soul(tmp_path, FULL_SOUL_MD)
    append_patch(tmp_path, "verb", "go_east", "go east")
    soul = parse_soul(tmp_path)
    intents = [v.intent for v in soul.verb_mappings]
    assert "go_east" in intents


# --- Context section tests ---


def test_context_empty_when_no_section(tmp_path):
    _write_soul(tmp_path, FULL_SOUL_MD)
    soul = parse_soul(tmp_path)
    assert soul.context == ""


def test_context_inline_text(tmp_path):
    content = FULL_SOUL_MD + "\n## Context\n\nUse `go north` to move.\n"
    _write_soul(tmp_path, content)
    soul = parse_soul(tmp_path)
    assert "go north" in soul.context


def test_context_link_resolves_to_file_content(tmp_path):
    ref = tmp_path / "ref.md"
    ref.write_text("# Commands\nUse @create to build objects.")
    content = FULL_SOUL_MD + f"\n## Context\n\n[Commands]({ref.name})\n"
    _write_soul(tmp_path, content)
    soul = parse_soul(tmp_path)
    assert "@create" in soul.context


def test_context_missing_link_target_uses_display_text(tmp_path):
    content = FULL_SOUL_MD + "\n## Context\n\n[Command Reference](nonexistent.md)\n"
    _write_soul(tmp_path, content)
    soul = parse_soul(tmp_path)
    assert "Command Reference" in soul.context


def test_context_multiple_links_all_resolved(tmp_path):
    ref_a = tmp_path / "a.md"
    ref_b = tmp_path / "b.md"
    ref_a.write_text("Content from A.")
    ref_b.write_text("Content from B.")
    content = FULL_SOUL_MD + f"\n## Context\n\n- [A]({ref_a.name})\n- [B]({ref_b.name})\n"
    _write_soul(tmp_path, content)
    soul = parse_soul(tmp_path)
    assert "Content from A." in soul.context
    assert "Content from B." in soul.context


def test_context_not_included_in_rules(tmp_path):
    ref = tmp_path / "ref.md"
    ref.write_text("- trigger -> action\n")
    content = FULL_SOUL_MD + f"\n## Context\n\n[Ref]({ref.name})\n"
    _write_soul(tmp_path, content)
    soul = parse_soul(tmp_path)
    # The rule-like line in the ref file must NOT be parsed as a rule
    patterns = [r.pattern for r in soul.rules]
    assert "trigger" not in patterns


def test_baseline_loaded_into_context(tmp_path):
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    soul_content = "# Name\nTestAgent\n\n# Mission\nTest mission.\n\n# Persona\nTest persona.\n"
    (agent_dir / "SOUL.md").write_text(soul_content)
    (tmp_path / "baseline.md").write_text("Baseline knowledge.")
    soul = parse_soul(agent_dir)
    assert "Baseline knowledge." in soul.context


def test_response_format_section_parsed_as_addendum(tmp_path):
    content = FULL_SOUL_MD + "\n## Response Format\n\nUse SCRIPT: for all build sequences.\n"
    _write_soul(tmp_path, content)
    soul = parse_soul(tmp_path)
    assert "SCRIPT:" in soul.addendum


def test_response_format_not_in_context(tmp_path):
    content = FULL_SOUL_MD + "\n## Response Format\n\nUse SCRIPT: for all build sequences.\n"
    _write_soul(tmp_path, content)
    soul = parse_soul(tmp_path)
    assert "SCRIPT:" not in soul.context


def test_unknown_h2_section_folded_into_context(tmp_path):
    content = FULL_SOUL_MD + "\n## Script Execution\n\nUse SCRIPT: to batch commands.\n"
    _write_soul(tmp_path, content)
    soul = parse_soul(tmp_path)
    assert "SCRIPT:" in soul.context
    assert "Script Execution" in soul.context


def test_unknown_h2_section_does_not_become_rule(tmp_path):
    content = FULL_SOUL_MD + "\n## Script Execution\n\nUse SCRIPT: cmd1 | cmd2.\n"
    _write_soul(tmp_path, content)
    soul = parse_soul(tmp_path)
    patterns = [r.pattern for r in soul.rules]
    assert not any("SCRIPT" in p for p in patterns)


def test_fenced_code_in_unknown_h2_folded_into_context(tmp_path):
    content = FULL_SOUL_MD + "\n## Script Execution\n\n```\nSCRIPT: go north | look\n```\n"
    _write_soul(tmp_path, content)
    soul = parse_soul(tmp_path)
    assert "go north" in soul.context


def test_fenced_code_in_context_section_included(tmp_path):
    content = FULL_SOUL_MD + "\n## Context\n\n```\nexample command\n```\n"
    _write_soul(tmp_path, content)
    soul = parse_soul(tmp_path)
    assert "example command" in soul.context


def test_context_in_system_prompt(tmp_path):
    from moo.agent.brain import Brain
    from moo.agent.config import LLMConfig, AgentConfig

    ref = tmp_path / "ref.md"
    ref.write_text("Always use @describe to set descriptions.")
    content = FULL_SOUL_MD + f"\n## Context\n\n[Ref]({ref.name})\n"
    _write_soul(tmp_path, content)
    soul = parse_soul(tmp_path)
    llm_cfg = LLMConfig(provider="anthropic", model="claude-haiku-4-5-20251001", api_key_env="ANTHROPIC_API_KEY")
    agent_cfg = AgentConfig(command_rate_per_second=1.0, memory_window_lines=10)

    Brain(
        soul,
        type("C", (), {"llm": llm_cfg, "agent": agent_cfg})(),
        send_command=lambda x: None,
        on_thought=lambda x: None,
        config_dir=tmp_path,
    )
    assert "@describe" in soul.context
