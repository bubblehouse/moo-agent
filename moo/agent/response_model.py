"""
Pydantic response model for one LLM cycle. Instructor validates the model's
reply against ``AgentResponse``; a failed validation is re-asked automatically.
See ``docs/source/explanation/agent-internals.md`` (Structured Responses).
"""

import re

from pydantic import BaseModel, Field, field_validator, model_validator

from moo.agent.tools import BUILDER_TOOLS_BY_NAME

# Strip Harmony/ChatML special tokens that local runtimes occasionally leak
# into string fields (e.g. ``<|im_start|>``).
_SPECIAL_TOKEN_RE = re.compile(r"<\|[^|>]+\|?>|<[A-Za-z_]\w*\|>")


def _scrub(text: str) -> str:
    """Remove leaked special tokens from a free-text field."""
    return _SPECIAL_TOKEN_RE.sub("", text).strip()


class Action(BaseModel):
    """One tool invocation. ``args`` is validated against the ToolSpec registry."""

    tool: str = Field(description="A registered tool name.")
    args: dict[str, str] = Field(
        default_factory=dict,
        description="Tool arguments as a flat string map.",
    )

    @field_validator("tool")
    @classmethod
    def _known_tool(cls, v: str) -> str:
        if v not in BUILDER_TOOLS_BY_NAME:
            raise ValueError(f"Unknown tool '{v}'. Valid tools: {', '.join(BUILDER_TOOLS_BY_NAME)}")
        return v

    @model_validator(mode="after")
    def _required_args(self) -> "Action":
        spec = BUILDER_TOOLS_BY_NAME.get(self.tool)
        if spec:
            missing = [p.name for p in spec.params if p.required and p.name not in self.args]
            if missing:
                raise ValueError(f"Tool '{self.tool}' missing required args: {missing}")
        return self


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
    """The single validated response shape for one LLM cycle."""

    reasoning: str = Field(
        default="",
        description="Brief private reasoning. Visible to you but never sent to the server.",
    )
    goal: str = Field(description="One-line current objective.")
    actions: list[Action] = Field(
        default_factory=list,
        description="Ordered tool calls to execute this cycle.",
    )
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
