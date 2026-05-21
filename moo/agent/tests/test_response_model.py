"""
Tests for moo/agent/response_model.py — the Pydantic AgentResponse schema
and its validators.
"""

import pytest
from pydantic import ValidationError

from moo.agent.response_model import Action, AgentResponse, SoulPatch


# --- Action ---


def test_action_accepts_known_tool():
    action = Action(tool="dig", args={"direction": "north", "room_name": "The Library"})
    assert action.tool == "dig"
    assert action.args["direction"] == "north"


def test_action_rejects_unknown_tool():
    with pytest.raises(ValidationError):
        Action(tool="frobnicate", args={})


def test_action_rejects_missing_required_arg():
    with pytest.raises(ValidationError):
        Action(tool="dig", args={"direction": "north"})  # room_name missing


def test_action_allows_optional_arg_omitted():
    action = Action(tool="look", args={})  # target is optional
    assert action.tool == "look"


def test_action_accepts_system_tools():
    assert Action(tool="raw", args={"command": "@realm $room"}).tool == "raw"
    assert Action(tool="respond", args={"message": "thinking"}).tool == "respond"


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
    assert resp.actions == []
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
        actions=[
            {"tool": "dig", "args": {"direction": "north", "room_name": "The Library"}},
            {"tool": "go", "args": {"direction": "north"}},
        ],
        done="Library built.",
        soul_patches=[{"kind": "note", "content": "save() after assigning name"}],
        build_plan="phase: East Wing",
    )
    assert len(resp.actions) == 2
    assert resp.actions[0].tool == "dig"
    assert resp.done == "Library built."
    assert resp.soul_patches[0].kind == "note"
    assert resp.build_plan == "phase: East Wing"


def test_agent_response_scrubs_special_tokens():
    """Leaked Harmony/ChatML tokens are stripped from free-text fields."""
    resp = AgentResponse(goal="<|im_start|>look around", reasoning="<|channel|>thinking")
    assert "<|" not in resp.goal
    assert "<|" not in resp.reasoning
    assert "look around" in resp.goal
