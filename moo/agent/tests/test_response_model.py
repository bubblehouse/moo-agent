"""
Tests for moo/agent/response_model.py — the Pydantic ``AgentResponse``
meta-state schema and its validators.

Stage-2: the per-tool ``Action``/``ActionUnion``/``ActionBase`` machinery and
the ``actions`` field are gone. Tool calls go through PydanticAI's native
tool-call channel; this module is now only meta-state (goal, plan, done,
soul_patches, build_plan) + free-text scrubbing.
"""

import pytest
from pydantic import ValidationError

from moo.agent.response_model import AgentResponse, SoulPatch


# --- SoulPatch ---


def test_soul_patch_kinds():
    for kind in ("rule", "verb", "note"):
        assert SoulPatch(kind=kind, content="x").kind == kind


def test_soul_patch_rejects_bad_kind():
    with pytest.raises(ValidationError):
        SoulPatch(kind="proverb", content="x")


# --- AgentResponse ---


def test_agent_response_minimal():
    resp = AgentResponse(goal="explore")
    assert resp.goal == "explore"
    assert resp.done is None
    assert resp.soul_patches == []
    assert resp.build_plan is None
    assert resp.plan is None  # None = leave the current plan unchanged


def test_agent_response_plan_field():
    resp = AgentResponse(goal="traverse", plan=["#9", "#22", "#37"])
    assert resp.plan == ["#9", "#22", "#37"]


def test_agent_response_full_round_trip():
    resp = AgentResponse(
        reasoning="I should build the room.",
        goal="build the library",
        done="Library built.",
        soul_patches=[{"kind": "note", "content": "save() after assigning name"}],
        build_plan="phase: East Wing",
    )
    assert resp.done == "Library built."
    assert resp.soul_patches[0].kind == "note"
    assert resp.build_plan == "phase: East Wing"


def test_agent_response_scrubs_special_tokens():
    """Leaked Harmony/ChatML tokens are stripped from free-text fields."""
    resp = AgentResponse(goal="<|im_start|>look around", reasoning="<|channel|>thinking")
    assert "<|" not in resp.goal
    assert "<|" not in resp.reasoning
    assert "look around" in resp.goal


def test_agent_response_no_actions_field():
    """Sanity: the legacy ``actions`` field is gone — no ``ToolName`` enum, no
    discriminated union — those live in the PydanticAI tool channel now."""
    assert "actions" not in dict(AgentResponse.model_fields)
