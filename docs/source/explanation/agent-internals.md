# Inside the Agent

`moo-agent` is the standalone CLI that signs into a DjangoMOO server as a
persistent player and acts on its own. The user-facing story is in the
[how-to guide](../how-to/moo-agent.md); the
[first-agent tutorial](../tutorials/first-agent.md) walks through a starter
run. This document is the explanation layer — *why* the agent is shaped the
way it is. Most of the load-bearing detail lives here so that the modules in
`moo/agent/` can stay short on inline commentary and just point back to the
relevant section.

## Architecture at a Glance

```
   ┌────────────────────────────────────────────────────────────────┐
   │  cli.py — wires everything, owns the SIGTERM/reconnect loop    │
   └──────────────┬───────────────────────────────────────┬─────────┘
                  │                                       │
                  ▼                                       ▼
   ┌──────────────────────────────┐          ┌────────────────────────┐
   │  connection.py               │          │  tui.py                │
   │   ├─ MooConnection (asyncssh)│          │   prompt-toolkit, two- │
   │   ├─ MooSession (PREFIX/     │          │   pane scrollback +    │
   │   │   SUFFIX delimiter mode) │          │   live input field     │
   │   └─ iac.py (telnet IAC)     │          └────────────┬───────────┘
   └──────────────┬───────────────┘                       │
                  │ on_output(text)                       │ operator input
                  ▼                                       ▼
   ┌────────────────────────────────────────────────────────────────┐
   │  brain/__init__.py — Brain                                     │
   │   ├─ output_queue (asyncio.Queue)                              │
   │   ├─ window (collections.deque, rolling output)                │
   │   ├─ script_queue (list[str], queued MOO commands)             │
   │   ├─ state (BrainState — current goal/plan/done flags)         │
   │   ├─ run()           — perception-action loop                  │
   │   ├─ _llm_cycle()    — one inference + dispatch                │
   │   ├─ _wakeup_loop()  — idle timer (timer-based agents)         │
   │   └─ _stall_check_loop() — token-chain stall recovery          │
   └──────────┬───────────────────────────┬─────────────────────────┘
              │                           │
              ▼                           ▼
   ┌────────────────────┐      ┌────────────────────────────┐
   │  brain/chain.py    │      │  llm_client.py             │
   │   server-text      │      │   provider selection,      │
   │   classifier;      │      │   text scrub, LM Studio    │
   │   token chain      │      │   text-fallback parsing    │
   │   relay & reconnect│      └────────────┬───────────────┘
   └────────────────────┘                   │
                                            ▼
              ┌──────────────────────────────────────────────┐
              │  tools.py — ToolSpec / BUILDER_TOOLS         │
              │   typed tool harness; native or text mode    │
              └──────────────────────────────────────────────┘
              ┌──────────────────────────────────────────────┐
              │  soul.py — SOUL.md, SOUL.patch.md, baseline  │
              └──────────────────────────────────────────────┘
              ┌──────────────────────────────────────────────┐
              │  brain/plans.py — build & traversal plan I/O │
              └──────────────────────────────────────────────┘
```

`Brain` never imports from `moo.core` and never triggers Django setup. It only
talks to the server through the `send_command` callback, and it only learns
about the world through `enqueue_output(text)`. That keeps the agent a thin
client of the MUD it inhabits, and lets the test suite drive `Brain` against
captured fixtures.

(perception-action-loop)=

## The Perception-Action Loop

`Brain.run()` is one coroutine that drains the output queue, decides what (if
anything) to do, and either fires the LLM or advances the script queue. The
state machine has only a few moving parts but they interact in awkward ways
because Celery, Kombu, and the SSH channel all deliver output on different
schedules.

### The `output_queue → window` flow

`enqueue_output()` is the single entry point for server text. It updates
`_last_activity` (used by the wakeup timer) and pushes the line onto an
`asyncio.Queue`. The run loop drains that queue with a 0.3-second timeout:

- **Got a line:** append to `window`, classify it through
  `process_server_text` (chain relay, plan extraction, [Mail] suppression),
  then either dispatch a matching reflexive rule, advance the script queue,
  or arm `pending_llm`.
- **Timed out (0.3 s of quiet):** flush `pending_drain`, `pending_llm`, or
  the fallback drain. This is the *quiet-period* edge that makes the rest of
  the loop work.

### Why drain after a quiet period

A single MOO command can produce a burst of output — a `tell()` block, plus
Celery `print()` preamble lines that arrive after the PREFIX/SUFFIX window of
the *next* command. If the script queue advanced on every individual line,
each preamble line would consume a script step and the agent would race
through its plan in milliseconds.

The fix is to set `pending_drain = True` whenever output arrives while the
script queue is non-empty, and only call `_drain_script()` after 0.3 s of
silence. By then the full burst has settled, and exactly one queued command
fires per response cycle.

Errors short-circuit this: if a server line matches `looks_like_error()`,
the script queue is cleared immediately and control returns to the LLM.

### The fallback drain

Some Celery-based verbs (`@create`, `@obvious`, `@alias`) emit their `print()`
output *after* the PREFIX/SUFFIX window, so it never reaches `run()` at all.
Without a fallback path, only the first command of a multi-step script
executes; the rest wait until the wakeup timer fires a fresh LLM cycle and
discards the queue. The fallback branch in `run()` checks for a queued script
on every quiet tick and drains one step even when no output arrived. After
the queue empties, an LLM cycle is queued so the agent can react to the
result — unless the agent is an orchestrator or `timer_only`, in which case
the cycle is suppressed.

### Pending-LLM gating

When server output arrives and no rule matches, `pending_llm = True` arms an
LLM cycle for the next quiet tick. Several conditions suppress that arming:

- **Page-triggered, no goal yet** — agents with `idle_wakeup_seconds == 0`
  and no `current_goal` ignore non-page output and stay in `WAITING` until a
  page lands. See {ref}`wakeup-modes`.
- **Orchestrator** — has no autonomous work; the token-chain relay in
  `chain.py` drives all of its commands deterministically.
- **`timer_only`** — fires only via the wakeup timer; output is recorded but
  never triggers inference.
- **`session_done`** — `done()` was called; status flips back to `READY` so
  the wakeup timer can still fire, but no LLM cycle runs until a fresh
  token page resets state.

(script-queue)=

## The Script Queue

`SCRIPT: a | b | c` directives, multi-step tool calls, and chain-relay
commands all funnel into `_script_queue`. The queue is just a `list[str]` of
raw MOO commands. `_drain_script()` pops one, writes it to the rolling window
prefixed with `>`, and sends it. Loop detection (`_check_command_loop`)
records the last 8 commands and injects an operator warning into the rolling
window if any single command repeats 3+ times.

### Tool calls override text-mode scripts

Some models (notably Gemma 4) emit *both* a structured tool call and a
`SCRIPT:` line in the same response, which would execute the same command
twice if the two queues were merged. `_dispatch_tool_calls` resolves this by
*replacing* the SCRIPT-derived queue when any tool call translates to
commands — native tool calls are authoritative.

### Done and `foreman_paged` guard

`done()` is special: it has no MOO command output but it sets
`session_done = True`, which suspends all further LLM cycles until a fresh
token page resets state. Calling `done()` before the agent has paged Foreman
with a "Token: …​ done." message would silently break the chain — Foreman
would never receive the handoff and the chain would stall.

The guard in `_dispatch_tool_calls` blocks `done()` until `foreman_paged`
flips to True, and rewrites the agent's `current_goal` to a CRITICAL
instruction telling it to send the page first. The bare-line fallback path
applies the same guard; both paths read `foreman_paged` from `BrainState`.

(llm-cycle)=

## One LLM Cycle

`_llm_cycle()` is gated by a `Semaphore(1)` so rapid output never queues
multiple in-flight calls — if a cycle is already running, the new one is
silently skipped. The cycle:

1. **Build the system prompt** via `brain/prompt.py:build_system_prompt`.
   When the agent has tools wired up, the tool-mode preamble is used and the
   tool schemas carry the action vocabulary; otherwise the full text-mode
   directive grammar is emitted.
2. **Build the user message** via `brain/prompt.py:build_user_message` from
   `memory_summary`, `current_goal`, `current_plan`, the idle-wakeup
   counter, and the rolling window.
3. **Call the LLM** via `llm_client.call_llm` with up to 3 retries on 529
   overload (5 s, 10 s, 20 s backoff).
4. **Parse the response** via `brain/directives.parse_llm_response` into an
   ordered list of `Directive` objects plus leftover thought lines.
5. **Apply directives** in source order. `GOAL:` updates `current_goal`,
   `PLAN:` rewrites the traversal plan, `SOUL_PATCH_*` appends to
   `SOUL.patch.md`, `BUILD_PLAN:` writes a YAML file under `builds/`,
   `SCRIPT:` populates the script queue, `DONE:` clears the goal, and
   `COMMAND:` is a one-shot dispatch.
6. **Dispatch tool calls** — dedupe consecutive duplicates (Gemma 4
   sometimes emits the same call list twice), translate each through its
   `ToolSpec.translate`, and queue the results. See {ref}`tool-harness`.

### The bare-line fallback

When neither a `COMMAND:` nor a `SCRIPT:` directive nor any tool calls were
emitted, but a `current_goal` is set, `_try_bare_line_fallback` rescues a
single-line response that *looks like* a MOO command. The heuristic is
deliberately tight to avoid sending English prose to the server's parser:

- The response must be exactly one non-empty line.
- The line must not be a bare directive keyword (`GOAL`, `PLAN`, `DONE`, …)
  or a parenthetical narration (`(Wait mode)`).
- The line either starts with a known MOO prefix (`@`, `say`, `page`,
  `look`, a compass direction) or is a short lowercase phrase (≤ 4 words,
  starting lowercase). Uppercase-first text is treated as English prose and
  discarded — `"Awaiting mason done page."` should never reach the server.
- If the line parses as a tool call against the registered tool set, it is
  translated and queued through the tool harness.

If even the fallback fails, an extra LLM cycle is queued (capped at 3 via
`goal_only_count`) so models that split goal-setting and action across
responses still get a chance to act. Orchestrators skip this — they have
nothing to "act on" while waiting for a token holder.

### The goal-only re-cycle counter

Some models (Gemma in particular) reliably emit a `GOAL:` line, then stop
without an action. The counter trips one extra cycle each time a goal is set
but no command is dispatched, capped at 3, so we don't enter an infinite
ping-pong if the model is stuck.

(wakeup-modes)=

## Wakeup Modes

Agents fall into one of three operating modes, determined by config flags.

### Timer-based (`idle_wakeup_seconds > 0`)

A background `_wakeup_loop` task fires an LLM cycle when the agent has been
idle for `idle_wakeup_seconds`. Within 10 seconds of firing, the prompt
flips to `SLEEPING` so the TUI can show countdown pressure.

When the timer fires, the agent's `current_goal` is cleared (timer agents
shouldn't loop on stale done/recap state), and optionally the rolling
window is cleared as well. Reactive NPCs that need accumulated room context
between wakeups can set `clear_window_on_wakeup = false`.

The timer skips if the plan is fully exhausted *and* the agent has no
current goal — at that point it has nothing left to do and would just
invent extra work.

### Page-triggered (`idle_wakeup_seconds == 0`)

Workers in the token chain (Mason, Tinker, Joiner, Harbinger) wait for a
page from Foreman that hands them the token. They don't run a wakeup loop
at all. The status flip in `_set_status` translates `READY` to `WAITING` so
the prompt shows `waiting>` while idle.

LLM cycles are suppressed unless the agent has a `current_goal` (token
received, work in progress) or an incoming line is a page. This prevents
the agent from burning tokens reasoning about server output that has
nothing to do with its job. The {ref}`token-chain` mechanics arrange for
the goal to be set automatically when a token page arrives.

### `timer_only`

Set on Foreman. The wakeup timer is the *only* path that fires LLM cycles —
output never arms `pending_llm`. This stops Foreman from over-reacting to
incoming chain pages between its scheduled cycles.

(stall-detection)=

## Stall Detection

`_stall_check_loop` is a deterministic recovery path that bypasses the LLM
entirely. It runs on Foreman (anywhere `stall_timeout_seconds > 0`) and
re-pages the agent currently holding the token if it hasn't emitted a "done"
page within the timeout.

Before re-paging, the loop shells out to `agentmux cycle-age` (configured
via `MOO_TOKEN_CHAIN_GROUP` and `MOO_AGENTMUX_PATH`) to ask whether the
target agent is still inside a plausible LLM cycle. If the agent's elapsed
time since its last log write is under `max(stall_s, 3 × p95)`, the
re-page is suppressed — the agent is just slow, not deadlocked. This
prevents Foreman from spamming an agent that's mid-inference on a slow
local model.

After firing, the dispatched timestamp resets so the next re-page fires one
full timeout later (linear backoff, not exponential).

(token-chain)=

## Token Chain Mechanics

`brain/chain.py:process_server_text` is a pure function that runs on every
inbound line. It classifies the line, mutates `BrainState` in place, and
returns a `ChainActions` value telling Brain which scripts to queue and
which thoughts to surface. Splitting it out of `Brain.run()` is what makes
the relay logic testable against captured fixtures (see
`tests/test_brain_chain.py`).

### Roles: orchestrator vs worker

`is_orchestrator = bool(token_chain) and ssh.user not in token_chain` — an
agent is the orchestrator when a chain is configured but the agent itself
isn't a member. Workers (chain members) inherit `MOO_TOKEN_CHAIN` from the
environment but must *not* relay; doing so would create an infinite
self-page loop.

### Auto-start on connect

When `text == "Connected"` and the orchestrator has no dispatched token
yet, it pages the first agent in the chain with "Token: Foreman start." and
records `token_dispatched_to`. No LLM call needed.

### Auto-relay

When an incoming page contains "Token: …​ done.", the orchestrator looks up
the sender's position in the chain and pages the next member (wrapping
back to the first if the sender was last). Workers see the same line but
skip relay because they're inside the chain.

### Auto-reconnect

When a worker logs in mid-pass, it sends `Token: <name> reconnected.` to
Foreman. Foreman re-pages that agent — but only if no token is currently
dispatched, or the dispatched target matches. This stops a batch startup
from flooding Foreman with reconnect pages that each get a token handed
back simultaneously.

Workers themselves use `prior_goal_for_reconnect` to fire the reconnect
page on their own connect event without waiting for an LLM cycle.

### Mailbox suppression

`[Mail] From <sender>: <body>` lines are extracted, recorded into
`memory_summary` as prior-session context, and *suppressed* from the
rolling window. The line itself never reaches the LLM; only the parsed
context does. This keeps the noise from `check_inbox` polling out of the
prompt.

### Auto-extracted plans

`divine()` returns a "Impressions surface…" header followed by indented
`<Name> (#NNN)` lines. Workers that need a traversal plan would otherwise
have to format a `PLAN:` directive themselves; smaller models (Gemma)
reliably stall on that step, setting a meta-goal like "prepare a plan"
instead of emitting the directive. `process_server_text` extracts the room
IDs directly into `current_plan`, so the agent can skip that step and go
straight to teleporting to the first room.

The extraction only fires when the plan is empty or was loaded from disk —
it never overwrites an active plan from a token page or a fresh
`BUILD_PLAN:`.

(plan-persistence)=

## Plan Persistence

`brain/plans.py` owns four free functions for plan I/O. Splitting them out
of `Brain` lets the persistence logic be tested against a plain
`BrainState` and a `tmp_path` directory.

### Build plans (Mason)

`save_build_plan` accepts a `BUILD_PLAN:` payload, writes it as a
datestamped YAML file to `builds/YYYY-MM-DD-HH-MM.yaml`, extracts top-level
room names via the indent-aware regex in `directives.py`, and overrides
`memory_summary` so the next LLM cycle starts *building* instead of
re-planning.

Only the first `BUILD_PLAN:` per session is accepted. If the plan is
already populated (from a prior plan or a disk reload), subsequent
`BUILD_PLAN:` directives are logged and ignored. The check has one
exception: a plan made of only room IDs (`#128`, `#9`, …) is treated as
visit-list context from a token page, and a real plan with room *names* is
allowed to override it.

### Traversal plans (workers)

`save_traversal_plan` writes `current_plan` to `builds/traversal_plan.txt`
on every change. `load_traversal_plan` restores it on startup. Workers
that don't emit `BUILD_PLAN:` (Tinker, Joiner, Harbinger) use this to
resume their room list after a restart. `load_latest_build_plan` runs
first; the traversal plan only loads if no build plan was found.

Page-triggered agents always start cold and receive fresh room lists via
the token, so the traversal plan is *not* loaded at construction time for
them — a stale plan from a previous mission would let the LLM skip
`divine()` on the next token pass and visit the wrong rooms.

(soul-system)=

## The Soul System

`soul.py` parses an agent's persona and operational rules from two files:

- `SOUL.md` — the immutable core. Mission, persona, optional context,
  reflexive `Rules of Engagement`, `Verb Mapping` intent shorthands, and
  the `Tools` list.
- `SOUL.patch.md` — append-only and agent-writable. The LLM emits
  `SOUL_PATCH_RULE:`, `SOUL_PATCH_VERB:`, and `SOUL_PATCH_NOTE:`
  directives that get appended via `append_patch_directive`. Notes
  document lessons learned without imposing a fixed response.

If a `baseline.md` exists in the config directory's *parent*, its text is
prepended to `SOUL.context` and any rules/verb mappings it contains are
appended to the soul's lists. This is how the four tradesmen agents share
a baseline persona while keeping per-agent specifics in their own
`SOUL.md`.

Markdown links in the `Context` section that resolve to local `.md` or
`.txt` files are inlined verbatim. The agent's persona file can therefore
pull in glossaries or shared playbooks without copy-paste.

(connection-layer)=

## The Connection Layer

`connection.py:MooConnection` opens an `asyncssh` channel with
`TERM=xterm-256-basic`, which puts the django-moo shell into raw mode and
enables IAC subnegotiation. The agent advertises itself as `moo-agent` via
TTYPE/MTTS, accepts GMCP/MSSP/EOR/CHARSET, and refuses MSP. See
{ref}`iac-layer` for the negotiation details.

### Surrogate-escape encoding

The channel is configured with `errors="surrogateescape"` so 0xFF IAC
bytes round-trip as `\udcff` Python str surrogates instead of raising
`UnicodeDecodeError`. Outbound IAC reply bytes are encoded with the same
mode and re-emitted by the channel verbatim.

### PREFIX/SUFFIX delimiter mode

After a session is up, `MooSession.setup_delimiters(prefix, suffix)`
switches the line buffer from "emit one line per `\n`" to "emit only the
content between `>>MOO-START-{id}<<` and `>>MOO-END-{id}<<` markers." The
delimiters are per-session (8-char hex of a fresh timestamp) so two
agents on the same broker don't ever cross-talk.

### Why no suppress window during setup

An earlier design suppressed all output between writing the setup
commands and switching to delimiter mode, so the verbs'
"Global output prefix set to…" confirmations would not pollute the
agent's log. The cost was that any page or tell from another player
landing in that window was silently extracted and dropped — Foreman's
initial token dispatch routinely missed Joiner because the page arrived
during Joiner's setup. The current design sends the setup commands in
line mode (so confirmations and incoming pages both come through as
visible server lines) and only flips to delimiter mode after settings
have propagated. The setup confirmations are bounded (≤ 6 lines, once
per session); a missed page costs minutes of stall recovery, so we
choose the noise.

### Kombu broker latency

Each `OUTPUTPREFIX` / `OUTPUTSUFFIX` / `a11y` verb publishes its session
setting via Kombu, and the shell's `process_messages()` needs to drain
the event into the server-side `_session_settings` dict before the *next*
command's wrapping logic reads it. Kombu publish→consume has 200 ms+ of
broker latency. The setup sequence sleeps 0.4 s between commands to give
each setting time to land before the next command's response is wrapped.

### Preamble extraction in delimiter mode

When delimiter mode finds a SUFFIX, it emits any complete preamble lines
*before* the most recent PREFIX as individual lines. This captures
`print()` output from a previous command that arrived after that
command's suffix (Celery flush order). Trailing partial content between
the last newline and the prefix marker is dropped — that's typically the
server's interactive prompt (`>>>` in raw mode), which should never
surface to the agent.

### Eager flush

After the regular delimiter extraction, `_extract_delimited` eagerly
flushes any complete lines that sit in the buffer ahead of the next
pending PREFIX. These are `print()` confirmations from commands whose
`tell()` output was empty — without the eager flush they would wait in
the buffer until the next command, causing the agent to see no
confirmation and retry the same command repeatedly.

(iac-layer)=

## IAC (Telnet Subnegotiation)

`iac.py` is the client-side mirror of the server's `moo/shell/iac.py`. It
splits into three pieces:

- **`IacParser`** — a byte-feed state machine that strips IAC sequences out
  of the data stream and emits parsed events (`("cmd", cmd, opt)`,
  `("sb", opt, payload)`, `("ga",)`, `("eor",)`).
- **Encoders** (`encode_cmd`, `encode_sb`, `encode_ttype_is`,
  `encode_naws`, `encode_gmcp`, `encode_charset_request`) — produce the
  reply byte sequences. `encode_sb` doubles 0xFF in payloads per the
  telnet escaping rule.
- **`AgentIacNegotiator`** — translates each parsed event into reply
  bytes and capability state changes. Side effects on negotiation
  completion (e.g. sending `Core.Hello` after GMCP enables) are emitted
  along with the immediate reply bytes.

### What we offer and accept

- `_WE_OFFER = {OPT_TTYPE, OPT_NAWS, OPT_CHARSET}` — the agent enables
  these on its own side when the server asks (`DO X` → reply `WILL X`).
- `_WE_ACCEPT_SERVER = {OPT_GMCP, OPT_MSSP, OPT_EOR_OPT, OPT_CHARSET}` —
  enabled on the server side when offered (`WILL X` → reply `DO X`).

MSP is intentionally omitted — we can't play sounds. SGA is omitted on
purpose: the server's `WONT SGA` is what enables `IAC GA` after each
prompt, which is the prompt-boundary signal the agent reads.

### Loop suppression

Servers that re-send `WILL`/`DO` when they see our `DO`/`WILL` (the
django-moo server does this for accepted client options) would otherwise
trigger an infinite ping-pong. The negotiator tracks already-enabled
options on `capabilities` and replies only when state actually changes;
already-refused options are tracked privately on `_refused_will` /
`_refused_do` so repeat WILL/DO from the server are silently ignored
without leaking sentinel keys into the public capabilities dict.

### TTYPE / MTTS handshake

The TTYPE handshake is a three-stage loop: stage 1 returns the client
name (`moo-agent`), stage 2 returns the terminal name
(`XTERM-256COLOR`), stage 3 returns `MTTS <bitfield>`. The default MTTS
bitfield advertises `ANSI | UTF-8 | 256-color | screen-reader` — the
screen-reader bit is the truthful flag because the agent reads the
output programmatically.

After stage 3, any further `IAC SB TTYPE SEND` requests loop on the
terminal name to signal we have nothing more to offer.

### GMCP handshake

When GMCP enables, `_send_gmcp_handshake` emits `Core.Hello` (with the
client name and version) and `Core.Supports.Set` advertising the packages
the agent consumes (default: `Char 1`, `Room 1`, `Comm 1`, `MSSP 1`). The
editor package is intentionally omitted — it requires programmatic
save/cancel that's out of scope for the current MR.

(llm-client)=

## The LLM Client

`llm_client.py` is the provider-agnostic call wrapper. Three pieces live
here:

- `make_client(llm_config)` — picks the right SDK
  (`AsyncAnthropic`, `AsyncAnthropicBedrock`, or `AsyncOpenAI` against an
  LM Studio base URL). Brain holds a single client instance for the
  lifetime of the session so LM Studio can keep its KV cache warm across
  calls.
- `parse_lm_studio_tool_calls(text, known_names)` — pure function. Four
  fallback strategies, tried in order, for extracting tool calls from
  plain-text output when LM Studio doesn't surface them through the
  OpenAI `tool_calls` field:
  1. `<tool_call>{json}</tool_call>` XML blocks.
  2. `<call:tool_name(key='value')>` tags.
  3. `TOOL: name arg=value` lines (via `parse_tool_line`).
  4. Bare `name(k='v')` function calls validated against `known_names`.
- `call_llm(...)` — the awaitable wrapper. For Anthropic/Bedrock, native
  tool use is requested when tools are non-empty. For LM Studio,
  structured `tool_calls` are tried first, then the text fallback.

### Special-token scrubbing

Some local models (e.g. `gpt-oss` with Harmony templates) emit tokens
like `<|channel>thought` or `<|im_start|>` into the assistant text. If
these land in `memory_summary` or the rolling window, the next request
to LM Studio fails with `Failed to parse input at pos 0: <|channel>...`.
`_SPECIAL_TOKEN_RE` strips two forms:

- `<|...|>` / `<|...>` — leading pipe, any content (e.g. `<|im_start|>`).
- `<word|>` — trailing pipe only (e.g. `<tool_call|>`).

The scrub runs on every LLM response and on every line read from a
prior session log (`session_log.py`).

### Observability

`observability.py` wires the agent into [Pydantic Logfire](https://logfire.pydantic.dev).
`setup_observability()` runs once at startup in `run_agent()`, before any LLM
client is built — it calls `logfire.configure()` and then
`instrument_anthropic()` / `instrument_openai()`, which patch the SDK classes
globally. Because Instructor patches those same clients, every LLM call (and
each Instructor re-ask retry) is traced with token usage, latency, and cost.

`Brain._llm_cycle` opens a `logfire.span("llm_cycle")` around `_run_cycle_body`;
the auto-instrumented LLM call nests under it through OpenTelemetry context, so
one trace carries the goal, the LLM call, token/cost figures, and an `outcome`
attribute (`dispatched`, `goal_only`, or `llm_failed`).

Tracing is opt-in by environment variable: `configure()` uses
`send_to_logfire="if-token-present"`, so traces ship only when `LOGFIRE_TOKEN`
is set. Without it the calls are a local no-op. `console=False` keeps Logfire
off stdout — the prompt_toolkit TUI would otherwise be corrupted.

(tool-harness)=

## The Tool Harness

`tools.py` defines `ToolParam`, `ToolSpec`, `LLMResponse`, and the
`BUILDER_TOOLS` registry. A `ToolSpec` carries a name, description, typed
parameter list, and a `translate(args) → list[str]` function. Translation
keeps MOO command syntax out of the LLM's output path: the model says
`dig(direction="north", room_name="The Library")` and the harness emits
`@dig north to "The Library"`.

### Why `_norm_ref` exists

LLMs routinely emit `target=22` or `obj=22` as tool args, which would
translate to `@survey 22` / `@move 22 to ...`. The MOO parser then tries
to look up an object literally named "22" in the current room and fails
with `There is no '22' here.` `_norm_ref` rewrites bare positive
integers to `#22` form at translation time, eliminating the entire class
of error without burdening the agents with a guidance rule.
Non-integer references (`#22`, `here`, `$player_start`,
`"mahogany desk"`) are passed through unchanged.

### Schema flavors

`to_anthropic_schema()` and `to_openai_schema()` produce the shapes each
provider expects. When tools are active, the system prompt switches to
`PATCH_INSTRUCTIONS_TOOLS_ACTIVE` so the LLM is told to call tools
rather than emit free-form COMMAND/SCRIPT directives — the action
vocabulary lives in the tool schemas.

### Three text-mode parsers

`parse_tool_line` accepts three formats so that LM Studio fallback paths
don't have to know which provider produced the text:

- `TOOL: name(key="value" key2="value2")` — explicit prefix (the
  documented form).
- `call:name{...}` / `tool_call:name{...}` / `tool_code:name(...)` —
  Gemma 4 native shape when LM Studio doesn't expose `tool_calls`.
  Gemma also wraps string values in `<|"|>...<|"|>` special tokens;
  `_strip_gemma_tokens` rewrites them to plain quotes before the
  key-value extractor runs.
- `name(k="v", k2="v2")` — bare Python-style call. Only matched when a
  `known_names` set is supplied, so MOO commands that happen to contain
  parentheses don't get misidentified as tool calls.

The argument regex (`_BARE_CALL_RE`) allows parentheses inside quoted
strings (single or double), so values like
`done(summary="Completed Gear Vault (#816)")` parse correctly. Without
the quoted-string alternation the regex would stop at the first `)`
inside the string and fail to match the whole call.

### Redundant-teleport suppression

`_dispatch_tool_calls` and the bare-line fallback both inspect
`teleport(destination=…)` calls and skip them when the destination
already names the agent's current room (by `#N` id or name). The skip
also pushes a synthetic line into the rolling window so the LLM sees
authoritative feedback in the next cycle. Without that injection the
silent skip produced no commands, no server output, and the
`goal_only_count` re-cycle would just emit the same teleport call again
on the next 1–3 follow-up cycles before stalling.

(session-log)=

## Session Resume

`session_log.py:read_prior_session` is the thin filesystem layer that
lets a fresh run pick up where the previous one left off. Logs are
named `YYYY-MM-DDTHH-MM-SS.log`, so lexicographic order equals
chronological order. The function reads the most recent prior log,
keeps only the entries whose kind is in `_RESUME_KINDS` (`action`,
`server`, `goal`, `thought`, `server_error`), and returns the last 40
of those plus the most recent `[Goal] …​` line.

A plan-exhausted marker (`[Plan] All planned rooms built.`) overrides
the normal summary and replaces it with a hard instruction to call
`done()` immediately. Otherwise, special-token scrubbing runs on every
included line so a poisoned prior log can't re-poison the new
session.

`cli.py` then decides what to do with the result:

- **Timer-based agents** discard both the prior summary and the prior
  goal — stale context causes them to skip mandatory first steps (e.g.
  mailmen skipping `@mail` listing).
- **Page-triggered agents** discard the prior summary but keep the
  prior goal *only* to feed the auto-reconnect page mechanism. The
  goal is never set as `current_goal` — the agent always starts cold
  and waits for a fresh token page.

(tui)=

## The TUI

`tui.py` builds a prompt-toolkit full-screen application with two
regions: a scrolling output pane on top and a single-line input field
on the bottom. The status indicator on the input prompt
(`ready`/`waiting`/`sleeping`/`thinking`) is updated by Brain via the
`on_status_change` callback.

The output pane uses a custom `_ScrollableOutputControl` that reports
`cursor_position` at the last logical line when autoscrolling. In
scroll mode (entered with Escape) the cursor tracks the viewport top,
which — combined with directly setting `Window.vertical_scroll` in the
key handlers — produces exact line-by-line and page scrolling.
`window_height` is captured each render so key handlers can compute
page jumps without calling any `render_info` API.

Operator input from the TUI bypasses the rolling window's normal
LLM-arming path: `enqueue_instruction` appends an `[Operator]:` line
and immediately schedules an LLM cycle, because a direct instruction
should always reach the LLM regardless of rule matches.

## Where to look next

- For the directive grammar the LLM is taught: `brain/prompt.py`
  contains `PATCH_INSTRUCTIONS` (the LLM-facing reference document).
- For the regex grammar that parses LLM responses:
  `brain/directives.py`.
- For tool definitions: `tools.py:BUILDER_TOOLS`.
- For the chain-relay test fixtures: `tests/test_brain_chain.py`.
- For the LambdaCore-style server-side counterpart: see the django-moo
  docs at `docs/source/explanation/shell-internals.md` — the agent's
  PREFIX/SUFFIX delimiters and `a11y` settings are configured against
  that shell.
