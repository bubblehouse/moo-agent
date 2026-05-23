# PydanticAI Stage 2 — native tool loop with per-action feedback

Date: 2026-05-23
Status: proposed — implementation not yet started

## Context

Stage 1 swapped the LLM client from `instructor` to PydanticAI but kept the
Stage-0 batched-action design: the model emits a list of typed `actions`
inside `AgentResponse`, the brain translates each to a MOO command string,
queues them, and drains the queue at the rate limiter. The model never sees
the result of action 1 before committing to action 5; the first error aborts
the rest of the batch and burns the cycle on a partial result.

Half of `tools.py` exists to compensate for this blind-batching:
direction-validation in `_go`, verb-test rejection in `_look`, `_norm_ref`
fixups, the `_AGENCY_TELEPORT` auto-prefix, the `_VERB_TEST_RE` guard. Each
is a workaround for "the model can't observe what happens next."

Stage 2 closes that loop. The ~40 `BUILDER_TOOLS` become native PydanticAI
`@agent.tool` functions; the model calls them through PydanticAI's
multi-turn tool loop; each tool dispatches its MOO command, awaits the
PREFIX/SUFFIX-bracketed server output, and returns that as a string the
model sees before deciding the next call. The batched-action design and
the `_script_queue` retire.

Stage-1 validation already confirmed LM Studio supports the loop:
`tool_choice: "auto"` and `"required"` work against `qwen3.5-9b-mlx`; only
the object form (force a specific named tool) is rejected. PydanticAI's
default ToolOutput mode uses the supported forms.

## Design decisions

- **Native `@agent.tool` registration replaces `ToolSpec.translate`.** Each
  current `_dig`, `_go`, `_describe`, etc. function becomes a coroutine
  registered on the Agent. The translation logic stays; what's new is the
  dispatch + await steps that wrap it.
- **PREFIX/SUFFIX is the request/response correlator for synchronous
  commands.** `MooConnection` gets a `request(command) -> str` method that
  sends the command, waits for the next SUFFIX, and returns the bracketed
  slice. Most tools — `look`, `go`, `survey`, `@show`, `@exits`, verb
  invocations, error responses — finish synchronously and fit cleanly.
- **Async (Celery) verbs use a bounded post-SUFFIX wait.** For known
  Celery-backed verbs (`@create`, `@dig`, `@burrow`, `@edit verb`,
  `@obvious`, `@alias`, `@describe`), `request()` waits up to N additional
  seconds after SUFFIX for lines matching a known ack pattern (the same
  patterns already in `chain.py` — `_DIG_SUCCESS_RE`, etc.). If the pattern
  arrives, fold it into the return value. If it times out, return the
  synchronous slice with `[async result pending]` appended; the late
  output then lands in the *next* tool call's pre-PREFIX buffer and is
  prepended to that tool's result so the model still sees it one turn
  later.
- **`AgentResponse.actions` field is removed.** The model emits tool calls
  through PydanticAI's tool-call channel, not via a list field in the
  structured response. `goal` / `plan` / `todos` / `done` / `soul_patches` /
  `build_plan` remain — they're meta-state, not actions.
- **`_dispatch_actions` and `_script_queue` retire.** The Brain perception
  loop keeps draining server text into the window and firing
  `_llm_cycle`, but each cycle is a single `await agent.run(user_msg)` —
  PydanticAI runs the tool loop internally; brain just awaits the
  structured response.
- **The system-prompt `render_tools` block is removed.** PydanticAI renders
  registered tools into the model's tool-description channel; duplicating
  in the system prompt is noise.
- **`raw` and `respond` stay as escape hatches.** `raw(command)` is a tool
  that takes an arbitrary MOO command string and runs it through `request()`
  — useful for commands without a dedicated tool. `respond(message)` writes
  to the thought channel without contacting the server (no MOO dispatch).
- **`done(summary)` becomes a tool with a side effect.** When called, it
  flips a `RunContext.deps` flag the brain inspects after the run completes
  (`_session_done = True`), same outcome as today.

## Architecture: before / after

Today (Stage 1):

```
Brain._run_cycle_body
  ├─ build_user_message
  ├─ agent.run(user_message)              # one model call, returns AgentResponse
  │    └─ AgentResponse.actions: [...]    # batched intent
  ├─ _apply_agent_response                # goal, plan, soul_patches, build_plan
  └─ _dispatch_actions                    # translate -> _script_queue
       └─ run() drains queue              # rate-limited, blind to results
```

Stage 2:

```
Brain._run_cycle_body
  ├─ build_user_message
  └─ agent.run(user_message)              # multi-turn loop inside PydanticAI
       ├─ model calls dig(direction, room_name)
       │    └─ MooConnection.request("@dig ...") -> "Dug an exit..."
       │       └─ model sees result, decides next call
       ├─ model calls go(direction)
       │    └─ MooConnection.request("go north") -> "<room description>"
       ├─ model calls describe(target, text)
       │    └─ ...
       └─ returns AgentResponse (goal, plan, done, etc. — no actions)
  └─ _apply_agent_response                # meta-state only; no script queue
```

## MooConnection.request() — the new building block

`moo/agent/connection.py` gets:

```python
async def request(self, command: str, *,
                  async_wait_s: float = 0.0,
                  async_pattern: re.Pattern | None = None) -> str:
    """Send a MOO command; return the PREFIX/SUFFIX-bracketed response.

    For synchronous commands, async_wait_s=0.0 (default) returns immediately
    after SUFFIX. For Celery-backed verbs, pass a non-zero async_wait_s and a
    pattern that matches the expected ack — the call waits up to async_wait_s
    after SUFFIX for a line matching the pattern, and folds it into the result.
    On timeout, the return value carries the synchronous slice plus a
    `[async result pending]` sentinel; the late output will be prepended to
    whichever tool call drains it next."""
```

This consolidates today's scattered drain logic (`_drain_script`,
`_handle_script_line`, the PREFIX/SUFFIX pre-buffer in `connection.py`)
into one awaitable per command.

## Critical files

| File | Change |
| ---- | ------ |
| `moo/agent/connection.py` | Add `MooConnection.request()` — dispatch one MOO command, await PREFIX/SUFFIX bracket, optional bounded async wait |
| `moo/agent/tools.py` | Convert `BUILDER_TOOLS` `ToolSpec` registry into `@agent.tool` functions registered against the Agent. Each function: (a) call existing translate logic to build the command string, (b) `await ctx.deps.connection.request(cmd, ...)`, (c) return the result. Mark Celery-backed verbs with their ack pattern. |
| `moo/agent/llm_client.py` | `make_agent` now wires tools onto the Agent. The `deps_type` carries the `MooConnection`, the rate limiter, and the brain's mutable session flags (`session_done`, `foreman_paged`, etc.) that side-effect tools need. |
| `moo/agent/brain/__init__.py` | Delete `_dispatch_actions`, `_script_queue`, `_drain_script`, `_handle_script_line`, the action-loop branches in `_run_cycle_body`, and `_BARE_DIRECTIVES`. `_run_cycle_body` becomes: `result = await self._agent.run(user_message, deps=self._make_deps()); self._apply_agent_response(result.output)`. `_apply_agent_response` keeps only meta-state handling (`goal`, `plan`/`todos`, `done`, `soul_patches`, `build_plan`). |
| `moo/agent/response_model.py` | Remove `Action`, `actions` field on `AgentResponse`, the `ToolName` Literal. `Action` and `BUILDER_TOOLS_BY_NAME` references go with them. |
| `moo/agent/brain/prompt.py` | Drop `render_tools` and the tools section from `build_system_prompt`. `RESPONSE_FORMAT` loses the actions-list paragraph. |
| `moo/agent/brain/chain.py` | Unchanged in scope but verify the auto-advance patterns (dig, page, etc.) still fire — the server-output stream is unchanged, only the dispatch side changes. |
| tests | `test_tools.py` rewrites to exercise the registered tools via PydanticAI `TestModel`/`FunctionModel`. `test_brain.py` loses all `_script_queue` / `_dispatch_actions` tests. New `test_connection.py` tests for `request()`'s sync + async-bounded paths. |

## Async-result handling — table per verb

| Verb | Async wait | Pattern |
| ---- | ---------- | ------- |
| `@dig`, `@burrow`, `@tunnel` | 3s | `_DIG_SUCCESS_RE` (already in `chain.py`) |
| `@create` | 3s | `^Created #\d+` / `^Transmuted #\d+` |
| `@edit verb` | 3s | `^Created verb` / `^Set verb` |
| `@obvious`, `@alias` | 2s | `^Set` / `^Added alias` |
| `@describe`, `@move`, `place`, `put`, `take`, `drop`, `open`, `close` | 0s | synchronous |
| `look`, `go`, `survey`, `@show`, `@exits`, `@rooms`, `@divine`, `teleport` | 0s | synchronous |
| `page`, `send_report`, `post_board`, `read_board`, `write_book`, `read_book`, `clear_topic` | 0s | synchronous |
| `raw` | 0s | synchronous (escape hatch) |
| `respond` | n/a | no MOO dispatch |
| `done` | n/a | no MOO dispatch; sets `deps.session_done = True` |

Numbers are starting points — tune from Logfire span durations after the
first live run.

## Steps

1. **LM Studio spike.** A throwaway script: PydanticAI Agent with
   `NativeOutput(AgentResponse-minus-actions)` AND two `@agent.tool` functions
   (one no-op, one that calls into a fake `request()`), against the live LM
   Studio endpoint. Verify the tools+structured-output combination works on
   `qwen3.5-9b-mlx` and the `reasoning_content` shim still applies cleanly.
   Confirm exception types match Stage 1 (`ModelHTTPError`,
   `UnexpectedModelBehavior`).
2. **`MooConnection.request()`.** Implement the per-command await against
   PREFIX/SUFFIX. Unit test the sync path; integration test the async-bounded
   path against a stub connection that emits delayed lines.
3. **Tool conversion.** Move each `BUILDER_TOOLS` entry from `tools.py` into
   an `@agent.tool` function (likely in a new `moo/agent/agent_tools.py` to
   keep them separate from any residual registry shape). Preserve the
   existing translate logic verbatim; only the dispatch + return are new.
   Side-effect tools (`page`, `done`) read/mutate `deps`.
4. **`make_agent` wiring.** Pass `deps_type` and register tools. The
   `Agent` becomes parameterised — each Brain instance creates its agent
   with its own connection + deps. (Today's "one agent for the session" KV
   warmth still holds since deps are per-run.)
5. **Brain simplification.** Delete the action dispatch path. `_run_cycle_body`
   becomes the small form shown above.
6. **`AgentResponse` slimming.** Remove `Action`, `actions`,
   `ToolName`. Update tests.
7. **System prompt cleanup.** Drop `render_tools` and the actions paragraph
   from `RESPONSE_FORMAT`.
8. **Logfire span attributes.** The `llm_cycle` span gains `tool_calls`
   from PydanticAI's nested spans (no longer a brain-counted field). Update
   `_emit_cycle_stats` to read from the PydanticAI run usage or drop the
   counter.
9. **Tests + lint.** Full sweep; expect non-trivial test churn.

## Verification

- Spike (step 1) passes against live LM Studio with both tools and
  structured output active.
- `uv run pytest -n auto moo/agent/tests/` green after migration.
- `uv run pylint --fail-under=8 moo/agent` ≥ threshold; `uv run ruff check`
  clean.
- **Live LM Studio**: restart the tradesmen via `agentmux restart`. Watch
  via Logfire that the `agent run` spans now contain nested tool-call spans
  (`dig`, `go`, `describe`, etc.), each with its own server-result return
  value. Confirm:
  - The model adapts mid-cycle on error (e.g. `Huh?` from a malformed
    command leads to a recovery tool call in the same `agent run`, not a
    blanked-out cycle).
  - Celery-verb late results (e.g. `Dug an exit...`) arrive either inside
    the originating tool's return (within the bounded wait) or in the next
    tool's pre-PREFIX prefix.
  - Cycle counts go DOWN per task — what used to be 5 cycles of recovery
    around one mistake becomes 1 cycle with mid-cycle tool calls.
- **Defensive scaffolding audit**: confirm we can delete or simplify the
  workarounds whose existence the feedback loop makes redundant — the
  `_VERB_TEST_RE` guard in `_look`, the `_VALID_DIRECTIONS` check in `_go`,
  the `_AGENCY_TELEPORT` auto-prefix on board/book tools, the redundant
  `_norm_ref` rewrites. Each was added because the model couldn't observe
  the error; now it can.

## Out of scope (deferred)

- **Server-side correlation tokens for Celery completions.** A
  django-moo-side change (the synchronous handler emits a sentinel when
  the Celery task completes, scoped to the agent's session) would replace
  the bounded-wait heuristic with deterministic correlation. Worth doing
  later once Stage 2 is bedded in.
- **Parallel tool calls.** PydanticAI supports parallel tool execution
  (`parallel_tool_calls=True` in OpenAI settings). MOO commands serialise
  through the rate limiter anyway, so v1 stays sequential.
- **Removing the token chain's batched `Token: X go` page mechanic.** That
  protocol is independent of the tool loop and stays as-is.

## Step-1 spike result (2026-05-23)

Live run against `qwen3.5-9b-mlx` on LM Studio with PydanticAI 1.x.

| Variant | Output type validates | Tools fire | Notes |
| --- | --- | --- | --- |
| `NativeOutput(LiteResponse)` + 2 tools | ✓ | ✗ | Model emits JSON directly via `TextPart`; no `ToolCallPart` ever produced. JSON-schema constrained decoding suppresses tool calls. |
| `LiteResponse` (no NativeOutput) | ✓ | ✓ | 6 tool calls over 6 turns, structured output delivered via auto-generated `final_result` tool. `r.usage.tool_calls=6`. |

**Decision:** drop `NativeOutput()` for LM Studio in `make_agent`. The
default ToolOutput path delivers structured output via the `final_result`
tool call — that channel coexists with `@agent.tool` registrations. Tool
calls fire reliably; the model engages the loop without prompt coercion.

Side findings:

- `reasoning_content` shim may be moot under ToolOutput — the model
  emits ThinkingPart but also populates `TextPart` and `ToolCallPart`, so
  `message.content` is no longer empty. Keep the shim as a no-op safety
  net for now; verify removable after the cutover.
- `r.usage.tool_calls` exists and counts tool invocations across the
  whole multi-turn run. The `llm_cycle` span's `tool_calls` attribute
  reads from there in step 8.
- Per-turn latency on this hardware was ~60-90s. Chain cycles will run
  slower than the batched mode; measure under production load and tune
  if needed (e.g. by trimming the system prompt further in step 7).

## Risks

- **PydanticAI tools + `NativeOutput` interaction on LM Studio.** PydanticAI
  may switch from `NativeOutput` to `ToolOutput` automatically once tools
  are registered (since `final_result` becomes a tool). On LM Studio with
  qwen, that changes the structured-output mechanism from JSON-schema
  constrained decoding to tool-call constrained decoding. Both should
  work per the Stage 1 tests, but it's a category shift worth pinning in
  the spike.
- **Rolling-window pollution from tool results.** Today the rolling window
  contains server text; the model sees it in the user message. With tools
  returning command results directly, the same text would appear *both* in
  the rolling window AND in tool-call results — double exposure. Mitigation:
  suppress tool-dispatched commands' SUFFIX-bracketed text from the rolling
  window (the dispatcher already knows the command boundaries).
- **Race between unsolicited server output and tool result capture.** A
  page from another player arriving mid-`request()` could interleave with
  the bracketed slice. PREFIX/SUFFIX is supposed to delimit only the
  dispatched command's output, but the implementation needs to handle
  interleaved unsolicited lines cleanly.
- **Small-model behavior change.** Qwen-9b under a multi-turn tool loop is
  a different prompt regime than Stage 1's single-shot structured call.
  Expect a tuning pass on cycle duration, retries, and SOUL.md wording
  (e.g. removing the `actions` paragraph and replacing with tool-call
  guidance).
