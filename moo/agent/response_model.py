"""
Pydantic response model for one LLM cycle. PydanticAI validates the model's
reply against ``AgentResponse``; a failed validation is re-asked automatically.
See ``docs/source/explanation/agent-internals.md`` (Structured Responses).

Stage-2: tool calls are dispatched via PydanticAI's native tool loop, so the
old ``actions`` field, per-tool ``ActionBase`` subclasses, and ``ToolName``
Literal are gone. ``AgentResponse`` now carries only meta-state (goal, plan,
done, soul_patches, build_plan) — actions live in the tool-call channel.
"""

import re

from pydantic import BaseModel, Field, field_validator

# Strip Harmony/ChatML special tokens that local runtimes occasionally leak
# into string fields (e.g. ``<|im_start|>``).
_SPECIAL_TOKEN_RE = re.compile(r"<\|[^|>]+\|?>|<[A-Za-z_]\w*\|>")


def _scrub(text: str) -> str:
    """Remove leaked special tokens from a free-text field."""
    return _SPECIAL_TOKEN_RE.sub("", text).strip()


class SoulPatch(BaseModel):
    """A learned-knowledge patch appended to SOUL.patch.md (was SOUL_PATCH_*)."""

    kind: str = Field(description="One of 'rule', 'verb', or 'note'.")
    content: str = Field(
        description="For rule/verb: 'pattern -> command'. For note: free text.",
    )

    @field_validator("kind")
    @classmethod
    def _known_kind(cls, v: str) -> str:
        if v not in ("rule", "verb", "note"):
            raise ValueError(f"Unknown soul-patch kind '{v}'. Use 'rule', 'verb', or 'note'.")
        return v


class AgentResponse(BaseModel):
    """The single validated meta-response shape for one LLM cycle."""

    reasoning: str = Field(
        default="",
        description="Brief private reasoning. Visible to you but never sent to the server.",
    )
    goal: str = Field(description="One-line current objective.")
    plan: list[str] | None = Field(
        default=None,
        description="Optional room-traversal plan — the ordered list of room IDs still to visit. "
        "Set it to record or revise your plan; leave null to keep the current plan unchanged.",
    )
    done: str | None = Field(
        default=None,
        description="A one-line summary when the goal is fully complete; null otherwise.",
    )
    soul_patches: list[SoulPatch] = Field(
        default_factory=list,
        description="Optional learned-knowledge patches.",
    )
    build_plan: str | None = Field(
        default=None,
        description="Optional YAML build plan for a new construction phase.",
    )

    @field_validator("reasoning", "goal")
    @classmethod
    def _scrub_text(cls, v: str) -> str:
        return _scrub(v)
