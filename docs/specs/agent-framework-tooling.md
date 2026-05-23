# Agent Framework Tooling — Discussion Summary

Date: 2026-05-22
Status: exploratory — no decisions committed

This is a working note from a discussion about reducing inefficiency in the
moo-agent framework after the Instructor refactor. It records the diagnosis and
the options considered; it is not an implementation plan.

## Where moo-agent stands today

Each Brain cycle is a single Instructor-patched LLM call:

1. Build a system prompt (soul + tool reference rendered as text by
   `render_tools`).
2. Build a user turn (rolling window of server output + `memory_summary` +
   goal/plan).
3. Get back one validated `AgentResponse`.
4. Translate its `actions` list into MOO command strings via the `ToolSpec`
   registry and run them through the script queue.

Provider selection is hand-branched in `make_client` / `call_llm` across
Anthropic, Bedrock, and LM Studio, including a manual `reasoning_content`
fallback for thinking models on MLX.

The design works. The `Literal` tool-name enum that constrains LM Studio's
JSON-schema decoder is a deliberate, good choice. The notes below are about the
inefficiencies that remain, not a criticism of the current approach.

## Diagnosis — three inefficiencies visible in the code

### 1. The model acts blind within a cycle

It emits N actions at once; the brain executes them; the first error aborts the
rest of the script (`_ERROR_PREFIXES` in `brain/__init__.py`). The model never
sees the result of action 1 before committing to action 5. A large share of
`tools.py` is defensive scaffolding that compensates for this — the
`_VERB_TEST_RE` rejection in `_look`, the `go()` direction validation,
`_norm_ref`, and the `_AGENCY_TELEPORT` prefix injected because "small models
can't forget."

### 2. No observability

Debugging is `session_log.py` plain text plus grepping tmux panes. The
agent-trainer skill exists specifically to read logs and tune behavior — it is a
manual eval loop with no instrumentation underneath. There is no per-cycle token
count, no cost figure, no trace of which tool call failed and why, no structured
diff between a good run and a bad one.

### 3. Provider handling is hand-rolled

`call_llm` and `summarize` each branch on `provider`, duplicate the LM Studio
`extra_body` assembly, and carry the MLX `reasoning_content` fallback inline.

## Tooling considered

### Pydantic Logfire — observability

Status: implemented (2026-05-22). See `moo/agent/observability.py`, the
`llm_cycle` span in `Brain`, and the Observability notes in the how-to and
agent-internals docs.

Highest-leverage, lowest-risk addition. Built on OpenTelemetry, from the Pydantic
team. Instruments Instructor-patched clients with roughly one line
(`logfire.instrument_anthropic()` / `instrument_openai()`) because Instructor
patches those same SDK clients. Yields per-cycle traces, token/cost tracking, and
tool-call inspection without touching `brain/`. Turns the agent-trainer workflow
from grep-archaeology into structured trace comparison. The same OTEL spans
export to a self-hosted Langfuse instance if cloud is undesirable.

### PydanticAI — addresses inefficiency #1

The agent-framework layer above Instructor: provider-agnostic (absorbs the
`make_client` branching), native tool registration, structured output, built-in
retries, message-history management, first-class Logfire integration. It runs the
multi-turn tool loop so the model sees each tool result before the next call.
The `ToolSpec.translate` layer stays as the MOO-command compiler; what changes is
that the brain feeds results back instead of batching blind.

Cost is real: a rewrite of `llm_client.py` and part of `brain/__init__.py`, and a
check that LM Studio's JSON-schema constraint still holds, since native
tool-calling is what LM Studio previously rejected. Treat as a contained spike on
one worker, not a commitment.

### LiteLLM — likely skip

A provider-abstraction proxy that would unify the three-way branching, but
PydanticAI already covers that. Relevant only if a proxy with separate
budget/caching controls is wanted for its own sake.

### Eval harness

The zork smoke test is already an eval (the 317/350 "Master" score). Logfire and
Langfuse both support dataset-based eval runs, which would let agent-trainer
measure a tuning change against a fixed scenario set instead of eyeballing the
next live run.

## Todo-list functionality

moo-agent already has a degenerate todo list: `BrainState.current_plan` is an
ordered list the brain advances as work completes, and `AgentResponse.plan` lets
the model revise it. The limitation is that it only holds room IDs. Other
multi-step intent — furnish this kitchen, write and test these verbs, place these
objects — lives only in the rolling window or the lossy `memory_summary`.

### Where a generalized todo list helps

- Cross-cycle task memory that survives window scroll and summarization. A
  structured `todos: [{content, status}]` list injected into the user message
  every cycle is lossless, unlike the 2-3 sentence `memory_summary`.
- Reconnect recovery. Persisted to disk like traversal plans in `plans.py`, a
  todo list lets a dropped worker resume mid-task instead of restarting from a
  one-line goal.
- Partial relief for the batched-blind problem (#1). The list is the connective
  tissue that makes incremental multi-cycle progress coherent without a full
  per-action feedback loop.
- A legible debugging artifact — statuses show exactly where a run stalled.

### The caveat

The room-traversal plan is reliable because the brain auto-advances it from
server output (`_DIG_SUCCESS_RE` in `chain.py`); it does not trust the model to
self-report. A todo list maintained by the model alone is less reliable on small
local models — they mark things done that aren't, or never update, and the list
becomes prompt-poisoning noise.

The design that fits the codebase: completion is inferred from server output
wherever a pattern exists (the dig-advance mechanism), and model-driven status
updates are the fallback only for steps with no observable signal. The model
proposes and revises content; the brain owns `completed` status as much as it
can.

### Concrete shape

- `TodoItem` model: `content: str`, `status: Literal["pending", "in_progress",
  "completed"]`. Add `todos: list[TodoItem]` to `AgentResponse` and `BrainState`.
- Persist alongside traversal plans in `plans.py` (`save_todos` / `load_todos`).
- Render the list into `build_user_message`, same slot as the existing
  `Remaining plan:` line.
- In `chain.py`, extend auto-advance: where server output confirms a step, flip
  the matching todo to `completed` without trusting the model.
- This subsumes `current_plan` (the room list becomes one kind of todo) and
  replaces `memory_summary` for task-progress purposes.

### Precedent

The todo list is now a named agent primitive. LangChain's deepagents ships a
built-in `write_todos` tool with the `{content, status}` shape and a
`TodoListMiddleware` that renders the list into state each turn. On the Pydantic
side, `pydantic-ai-todo` adds hierarchical todos with subtasks, dependencies, and
persistence to any PydanticAI agent. If the PydanticAI spike proceeds, this comes
largely for free; if not, the `{content, status}` array plus brain-owned
completion is a small, self-contained addition.

## Suggested order of work

1. Add Logfire instrumentation. Few lines, no architectural risk, makes every
   later decision evidence-based. (Done — 2026-05-22.)
2. Add the todo list. An extension of a mechanism that already exists; does not
   require leaving Instructor; stands on its own.
3. Run a contained PydanticAI spike on one worker to measure whether a
   per-action feedback loop cuts error-recovery cycles. If it does, that is where
   the real inefficiency is, and much of `tools.py` defensive scaffolding could
   be retired.

## References

- Python AI Agent Library Comparison 2026 — Pydantic AI vs Instructor vs
  Smolagents: <https://jangwook.net/en/blog/en/python-ai-agent-library-comparison-2026/>
- Pydantic AI documentation: <https://ai.pydantic.dev/>
- AI & LLM Observability — Pydantic Logfire:
  <https://logfire.pydantic.dev/docs/ai-observability/>
- Langfuse — open source LLM engineering platform:
  <https://github.com/langfuse/langfuse>
- Todo list — LangChain deepagents docs:
  <https://docs.langchain.com/oss/python/deepagents/frontend/todo-list>
- pydantic-ai-todo — task planning toolset for PydanticAI:
  <https://github.com/vstorm-co/pydantic-ai-todo>
