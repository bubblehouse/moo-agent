"""
Tests for moo/agent/brain.py.

Tests rule matching, intent resolution, and compile_rules — no LLM calls, no
asyncio runtime needed for the pure logic paths. Does not require
DJANGO_SETTINGS_MODULE.
"""
# pylint: disable=protected-access

import re
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from moo.agent.brain import Brain
from moo.agent.soul import Rule, Soul, VerbMapping, compile_rules


@dataclass
class _FakeAgentConfig:
    command_rate_per_second: float = 10.0
    memory_window_lines: int = 50


@dataclass
class _FakeLLMConfig:
    provider: str = "anthropic"
    model: str = "claude-opus-4-6"
    api_key_env: str = "ANTHROPIC_API_KEY"


@dataclass
class _FakeConfig:
    agent: _FakeAgentConfig = None
    llm: _FakeLLMConfig = None

    def __post_init__(self):
        if self.agent is None:
            self.agent = _FakeAgentConfig()
        if self.llm is None:
            self.llm = _FakeLLMConfig()


def _make_brain(soul=None, config_dir=None):
    if soul is None:
        soul = Soul()
    config = _FakeConfig()
    sent = []
    thoughts = []
    brain = Brain(
        soul=soul,
        config=config,
        send_command=sent.append,
        on_thought=thoughts.append,
        config_dir=config_dir,
    )
    return brain, sent, thoughts


def test_check_rules_match():
    soul = Soul(rules=[Rule(pattern="^You feel hungry", command="eat food")])
    brain, _, _ = _make_brain(soul)
    brain._compiled_rules = compile_rules(soul)
    result = brain._check_rules("You feel hungry in the Manor")
    assert result == "eat food"


def test_check_rules_no_match():
    soul = Soul(rules=[Rule(pattern="^You feel hungry", command="eat food")])
    brain, _, _ = _make_brain(soul)
    brain._compiled_rules = compile_rules(soul)
    result = brain._check_rules("The room is bright and cheerful")
    assert result is None


def test_check_rules_first_match_wins():
    soul = Soul(
        rules=[
            Rule(pattern="hungry", command="eat food"),
            Rule(pattern="hungry", command="drink water"),
        ]
    )
    brain, _, _ = _make_brain(soul)
    brain._compiled_rules = compile_rules(soul)
    result = brain._check_rules("You feel hungry")
    assert result == "eat food"


def test_resolve_intent_known():
    soul = Soul(verb_mappings=[VerbMapping(intent="look_around", template="look")])
    brain, _, _ = _make_brain(soul)
    result = brain._resolve_intent("look_around")
    assert result == "look"


def test_resolve_intent_case_insensitive():
    soul = Soul(verb_mappings=[VerbMapping(intent="Look_Around", template="look")])
    brain, _, _ = _make_brain(soul)
    result = brain._resolve_intent("look_around")
    assert result == "look"


def test_resolve_intent_unknown_passthrough():
    soul = Soul()
    brain, _, _ = _make_brain(soul)
    result = brain._resolve_intent("go north")
    assert result == "go north"


def test_compile_rules_empty():
    soul = Soul()
    compiled = compile_rules(soul)
    assert compiled == []


def test_compile_rules_returns_patterns():
    soul = Soul(
        rules=[
            Rule(pattern="^hungry", command="eat"),
            Rule(pattern="(?i)ring.*bell", command="say Hello"),
        ]
    )
    compiled = compile_rules(soul)
    assert len(compiled) == 2
    assert all(isinstance(p, re.Pattern) for p, _ in compiled)
    pattern0, _ = compiled[0]
    assert pattern0.search("hungry now")
    assert not pattern0.search("  hungry now")  # ^ anchor


def test_apply_patch_updates_rules(tmp_path):
    soul_content = "# Name\nTest\n# Mission\nM\n# Persona\nP\n"
    (tmp_path / "SOUL.md").write_text(soul_content)
    soul = Soul()
    brain, _, _ = _make_brain(soul, config_dir=tmp_path)
    brain._apply_patch("rule", "^You are thirsty -> drink water")
    assert any(r.pattern == "^You are thirsty" for r in brain._soul.rules)


def test_apply_patch_bad_directive_ignored(tmp_path):
    soul_content = "# Name\nTest\n# Mission\nM\n# Persona\nP\n"
    (tmp_path / "SOUL.md").write_text(soul_content)
    soul = Soul()
    brain, _, _ = _make_brain(soul, config_dir=tmp_path)
    # No arrow — should be silently ignored
    brain._apply_patch("rule", "no arrow here")
    assert brain._soul.rules == []


def test_apply_patch_no_config_dir_noop():
    soul = Soul()
    brain, _, _ = _make_brain(soul, config_dir=None)
    brain._apply_patch("rule", "trigger -> command")
    # Should not raise; soul remains empty
    assert brain._soul.rules == []
