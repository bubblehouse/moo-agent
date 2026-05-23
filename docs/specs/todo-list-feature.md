# Add a structured todo list to moo-agent (v1)

Date: 2026-05-23
Status: proposed — implementation not yet started

## Context

moo-agent already has a degenerate todo list: `BrainState.current_plan: list[str]`
is an ordered list of room IDs the brain advances on `@dig` success. Everything
*else* the model is trying to accomplish — furnishing a room, writing and
testing verbs, placing objects across multiple cycles — lives nowhere durable.
It sits in the rolling window and scrolls off, or gets summarized into the lossy
`memory_summary`. Multi-cycle tasks lose coherence; reconnecting workers can't
resume mid-task; the agent-trainer workflow has no legible artifact showing
where a run stalled.

This spec adds a structured per-session todo list, parallel to the existing
`current_plan` (not replacing it yet), that the model revises via its
`AgentResponse` each cycle and the brain auto-completes from server output
wherever a pattern exists.

The user asked specifically about the `pydantic-ai-todo` library. Investigation
showed it ships a hard `asyncpg` dep (even when using in-memory storage) and its
`TodoCapability` integrates via `@agent.tool` registration — which Stage 1 of
the PydanticAI migration deliberately does not use (we still emit batched
actions inside `AgentResponse`). Using the library directly would either pull
Postgres or require jumping ahead to Stage 2. The library's *valuable*
contribution is its schema design and prompt-injection pattern, both of which
this design borrows without taking the dependency.

## Design decisions

- **Native implementation, not pydantic-ai-todo.** Borrow the schema
  (`content` + `active_form` + status enum) and the system-prompt
  injection pattern. Skip subtasks, dependencies, events, multi-tenancy.
- **Coexist with `current_plan`, don't subsume it.** `current_plan` is the
  canonical room-traversal mechanism with battle-tested auto-advance in
  `chain.py` and a `plan_exhausted` flag that gates foreman-paging. Subsuming
  it touches too many call sites for v1. Todos are additive: they cover
  non-room multi-cycle work (verb tests, furnishing sequences, recovery
  plans). Subsumption is a follow-up.
- **Whole-list revision, no per-item tools.** The model revises
  `AgentResponse.todos: list[TodoItem] | None` each cycle — same mechanism
  as today's `plan: list[str] | None`. Brain replaces `state.todos` and
  persists. No `add_todo` / `set_status` tools needed.
- **Brain owns `completed` where it can.** Server-output-driven auto-advance
  (existing `_DIG_SUCCESS_RE` + new patterns) flips matching todos to
  `completed` without trusting the model — same robustness pattern that
  makes `current_plan` reliable. Model-driven status updates are the fallback
  for steps with no observable signal.
- **Side fix bundled in:** rename the PydanticAI agent from the default
  `"agent"` to `"moo-agent"` in `make_agent`. Logfire then shows
  service=`mason+bijaz.local` / agent=`moo-agent` instead of generic `agent`.

## Schema

```python
# moo/agent/response_model.py
class TodoItem(BaseModel):
    id: str = Field(default_factory=lambda: secrets.token_hex(4))
    content: str  # imperative — "Build the kitchen"
    active_form: str = ""  # optional present-continuous — "Building the kitchen"
    status: Literal["pending", "in_progress", "completed", "blocked"] = "pending"
```

`AgentResponse` gains:

```python
todos: list[TodoItem] | None = Field(
    default=None,
    description="Optional structured task list. Set to record or revise; "
                "leave null to keep the current list unchanged. Items already "
                "marked completed by the brain stay completed.",
)
```

Brain merge rule: when `resp.todos is not None`, replace `state.todos` with it
— **except** that items currently in `state.todos` with `status == "completed"`
override the incoming status (brain's auto-completions can't be undone by the
model proposing a regression).

## Critical files

| File | Change |
| ---- | ------ |
| `moo/agent/response_model.py` | Add `TodoItem`; add `todos` field to `AgentResponse` |
| `moo/agent/brain/state.py` | Add `todos: list[TodoItem]` to `BrainState` |
| `moo/agent/brain/plans.py` | New `save_todos` / `load_todos` for `builds/todos.json` (mirror existing `save_traversal_plan` shape) |
| `moo/agent/brain/__init__.py` | `_apply_agent_response`: merge + persist todos when `resp.todos is not None`. `__init__`: call `load_todos`. Reuse the existing brain `_on_thought` channel for `[Todos]` updates. |
| `moo/agent/brain/chain.py` | Extend the existing `_DIG_SUCCESS_RE` block in `process_server_text`: when a dig succeeds, flip any pending todo whose `content` mentions the dug room name to `completed`. (Same shape as the existing `state.current_plan` advance.) |
| `moo/agent/brain/prompt.py` | `build_user_message`: render `state.todos` into the user turn (parallel to the existing `Remaining plan:` line). `RESPONSE_FORMAT` in the system prompt: one-line mention of the `todos` field and the whole-list-revision protocol. |
| `moo/agent/llm_client.py` | **Side fix:** pass `name="moo-agent"` to `Agent(...)` in `make_agent` |
| tests | New: `test_response_model.py` (TodoItem + AgentResponse.todos), `test_brain.py` (apply + merge override + auto-complete via dig), `test_brain_plans.py` (save/load roundtrip) |

## Auto-completion via server output

`chain.py` already extracts the dug room name from `_DIG_SUCCESS_RE` and pops
from `state.current_plan`. In the same block, after the existing plan-advance:

```python
for todo in state.todos:
    if todo.status == "pending" and dug_name.lower() in todo.content.lower():
        todo.status = "completed"
        actions.thoughts.append(f"[Todos] Completed: {todo.content}")
```

Only dig-success in v1. Other auto-completion hooks (verb-write confirmations,
object-create confirmations) come in a follow-up once we see what model
behavior actually looks like with todos in the loop.

## Steps

1. Add `TodoItem` + `AgentResponse.todos` in `response_model.py`. Unit test.
2. Add `BrainState.todos`. Add `save_todos` / `load_todos` in `plans.py`. Unit
   test the roundtrip.
3. `Brain.__init__`: call `load_todos` alongside the existing plan loads.
4. `_apply_agent_response`: merge + persist when `resp.todos is not None`,
   preserving brain-owned `completed` status.
5. `prompt.py`: render `state.todos` in `build_user_message`; one line in
   `RESPONSE_FORMAT` describing the field.
6. `chain.py`: dig-success todo auto-completion.
7. `llm_client.py`: side-fix the Agent name to `"moo-agent"`.
8. Tests for each step. Lint + ruff format.

## Verification

- `uv run pytest -n auto moo/agent/tests/` green; new tests cover the merge
  rule (brain-owned `completed` survives a model-proposed regression), the
  persistence roundtrip, and the dig-success auto-advance.
- `uv run pylint --fail-under=8 moo/agent` ≥ threshold; `uv run ruff check` clean.
- **Live LM Studio**: restart the tradesmen via `agentmux restart`. Give Mason
  a multi-step instruction via the tmux operator pane (e.g. "build the kitchen,
  pantry, and dining room"). Confirm:
  - `state.todos` populates from Mason's `AgentResponse.todos`.
  - `builds/todos.json` exists and reflects current state.
  - After each successful `@dig`, the matching todo flips to `completed` in the
    file and the next cycle's user message shows updated status.
  - Logfire spans now show agent name `moo-agent` (instead of `agent`).

## Out of scope (follow-ups)

- Subsuming `current_plan` into the todo list entirely.
- Subtasks / dependencies.
- More auto-completion hooks (verb writes, object creates).
- Native `@agent.tool` registration for fine-grained todo manipulation
  (`add_todo`, `update_status`) — depends on Stage 2 of the PydanticAI
  migration.
