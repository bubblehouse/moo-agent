# Running Your First Autonomous Agent

This tutorial walks you through creating and running an LLM-powered agent that connects to a DjangoMOO server as a persistent player and acts autonomously. The tutorial has two parts: building a simple greeter agent from scratch so you understand the mechanics, then a tour of the pre-built agent set that ships with the repo.

## Prerequisites

Before you start:

- A running DjangoMOO server with at least one player account you can use for the agent
- `moo-agent` installed (`uv sync` in the project root makes it available)
- An LLM provider credential: an Anthropic API key (`ANTHROPIC_API_KEY`) or a running LM Studio server

## Part A: Build a Greeter Agent

### Step 1: Create a player account for the agent

```bash
python manage.py createsuperuser --username greeter
python manage.py moo_enableuser greeter Greeter
```

The first command creates a Django user. The second links it to a MOO player object named `Greeter`. The `--wizard` flag is omitted here — the greeter doesn't need admin access.

### Step 2: Scaffold the config directory

```bash
moo-agent init --output-dir ./greeter --name Greeter --host localhost --port 8022 --user greeter
```

This creates:

```
greeter/
  SOUL.md           # Agent identity (edit this)
  SOUL.patch.md     # Learned behaviors (managed at runtime)
  settings.toml     # SSH and LLM config (fill this in)
```

### Step 3: Configure settings.toml

Open `greeter/settings.toml` and fill in the password and LLM provider:

```toml
[ssh]
host = "localhost"
port = 8022
user = "greeter"
password = "your-password-here"
key_file = ""

[llm]
provider = "anthropic"
model = "claude-opus-4-6"
api_key_env = "ANTHROPIC_API_KEY"

[agent]
command_rate_per_second = 1.0
memory_window_lines = 30
idle_wakeup_seconds = 30.0
max_tokens = 1024
```

`idle_wakeup_seconds = 30.0` means the agent will run an LLM cycle every 30 seconds even if no server output arrives. Good for a greeter that occasionally says something. Set it to `0` for an agent that only wakes when a page arrives.

For LM Studio instead of Anthropic:

```toml
[llm]
provider = "lm_studio"
model = "your-model-name"
base_url = "http://localhost:1234/v1"
```

### Step 4: Edit SOUL.md

Open `greeter/SOUL.md` and replace the template with:

```markdown
# Name
Greeter

# Mission
You are Greeter, a friendly presence in a DjangoMOO world. Your purpose is to
welcome new arrivals, answer basic questions about the world, and keep the
atmosphere warm. You respond to pages and greet players who speak to you.

# Persona
You are cheerful and concise. Keep responses to one or two sentences. Use plain
language — no flowery speech, no excessive formality.

## Rules of Engagement
- `^Connected` -> look
- `(?i)hello.*greeter` -> say Hello there! Welcome to the world.
- `(?i)help.*greeter` -> say I'm just a friendly bot. Try 'look' to see your surroundings.

## Verb Mapping
- greet_room -> say Greetings, everyone!
- check_surroundings -> look
```

The six sections:

| Section | Purpose |
|---------|---------|
| `# Name` | In-world name — must match the player object |
| `# Mission` | Seeded into the LLM system prompt |
| `# Persona` | Tone and style appended to the system prompt |
| `## Rules of Engagement` | Reflexive triggers — pattern matched against server output without LLM involvement |
| `## Verb Mapping` | Intent-to-command translations the LLM can use |

The `^Connected` rule fires when the server sends the login confirmation. The agent calls `look` immediately, which triggers any `^You arrive` rule if present (add one if you want the agent to announce itself on arrival).

### Step 5: Run the agent

```bash
export ANTHROPIC_API_KEY=sk-ant-...
moo-agent run ./greeter
```

The TUI opens. You'll see:

```
[system]  Connecting to localhost:8022...
[system]  Connected as Greeter
[server]  The Laboratory(#3)
[server]  ...
[action]  look
[server]  The Laboratory(#3)
[server]  A cavernous laboratory...
```

The `^Connected` rule fired and sent `look`. The agent is now live.

### Step 6: Interact with the agent

Open a second terminal and connect as Wizard:

```bash
ssh -p 8022 Wizard@localhost
```

Type `hello greeter` in the room where Greeter is. In the agent TUI you'll see:

```
[server]  Wizard says, "hello greeter"
[action]  say Hello there! Welcome to the world.
```

The rule matched and fired immediately — no LLM call was made.

Now send an operator instruction by typing into the TUI input field (the line at the bottom):

```
go to The Laboratory and introduce yourself
```

The agent receives this as an `[Operator]:` message and runs an LLM cycle. Watch the TUI show reasoning text (`[thought]`), then a `[action]` line with the command.

### Step 7: Observe soul patching

If the LLM emits a `SOUL_PATCH_RULE:` or `SOUL_PATCH_NOTE:` directive, the agent writes it to `greeter/SOUL.patch.md` and shows it in the TUI as a `[patch]` entry. Open `SOUL.patch.md` to see what was learned.

To reset learned behavior without changing the agent's identity, delete `SOUL.patch.md`. The file is recreated empty on the next run.

### Step 8: Exit

Press `Ctrl-C`, `Ctrl-D`, or `Ctrl-Q`. The agent sends `@quit` before disconnecting.

### What just happened

The agent's perception-action loop:

1. Server output arrives → the rule engine checks all `## Rules of Engagement` patterns using `re.search()`
2. If a pattern matches → the corresponding command is dispatched immediately, no LLM call
3. If no rule matches → an LLM cycle runs with the rolling context window as input
4. The LLM response is parsed for `GOAL:`, `COMMAND:` / `SCRIPT:`, and `DONE:` directives
5. Commands are dispatched; `SCRIPT:` commands queue multiple steps drained one at a time

`SOUL.patch.md` accumulates learned rules and notes across sessions. `baseline.md` in the parent directory (if present) provides shared world knowledge for all agents — it is prepended to the system prompt before `SOUL.md`.

---

## Part B: The Pre-Built Agent Set

The `extras/agents/` directory ships two distinct agent systems: **The Tradesmen** (a cooperative world-building chain) and **The Mailmen** (character-driven entertainment agents).

### The Tradesmen — Cooperative World Builders

The Tradesmen are six specialized agents that share work via a token-passing protocol. Only the token-holder acts; the others wait idle with `idle_wakeup_seconds = 0`. **Foreman** orchestrates the chain:

```
Foreman → Mason → Tinker → Joiner → Harbinger → Stocker → (back to Mason)
```

Each worker completes its domain, then pages Foreman: `page foreman Token: Mason done. Rooms: #9,#22,#31`. Foreman relays the room list and token to the next worker. The chain loops indefinitely, expanding the world on each pass.

Foreman uses `stall_timeout_seconds = 300` — if a worker goes silent for five minutes, Foreman re-pages it automatically. This is a deterministic wall-clock check in `brain.py`, not an LLM-based countdown.

To launch all agents at once, use the `agentmux` script:

```bash
extras/skills/agent-trainer/scripts/agentmux start
extras/skills/agent-trainer/scripts/agentmux restart mason
extras/skills/agent-trainer/scripts/agentmux stop
```

**Foreman** (`$player`, `extras/agents/foreman/`) — pure orchestrator. Never builds, describes, or modifies the world. Only `page()` and `say`. Holds the master token and relay room lists. Detects stalls with a five-minute deterministic timer.

**Mason** (`$player`, `extras/agents/mason/`) — room architect. Emits an upfront `BUILD_PLAN:` listing all intended rooms before building anything. Uses the `burrow()` tool exclusively — it creates the forward exit, new room, moves Mason into it, and wires the return exit atomically. Mason enforces spatial logic: alternate compass directions, no more than three in a row in one direction, perpendicular branching. Never creates objects, furniture, NPCs, or verbs.

**Tinker** (`$programmer`, `extras/agents/tinker/`) — interactive object creator. Creates `$thing` objects with Python verb behaviors. Uses the `write_verb()` tool which auto-injects the shebang, `--on`, and `--dspec` so the LLM never formats it manually. Common patterns: random response, state toggle (on/off), one-shot state change, cooldown timer, and secret exits (a `$thing` with a verb that calls `context.player.moveto(lookup(...))`). Needs `$programmer` access because it writes verbs via `@edit` and runs `@eval`.

**Joiner** (`$player`, `extras/agents/joiner/`) — furniture and container creator. Creates `$furniture` (sittable immovable fixtures) and `$container` (openable objects that hold items). Only needs `$player` access — no verb writing. Key distinction: `$furniture` cannot hold items, only `$container` can. Joiner never calls `describe()` on rooms (Mason's territory) or `obvious()` on exits.

**Harbinger** (`$programmer`, `extras/agents/harbinger/`) — NPC creator. Rolls `random(0–1)` per room and only creates an NPC if the roll ≤ 0.10 (roughly 10% of rooms get one). Each NPC is a `$player` child with a `tell` verb override and a `lines` property. The tell verb uses `announce_all_but(this, message)` — never `announce_all()`, which would cause infinite recursion by calling `tell` on the NPC itself. Dialogue is specific and slightly odd: three to six lines per NPC, never generic greetings.

**Stocker** (`$programmer`, `extras/agents/stocker/`) — consumable and dispenser creator. Stocks `$container` objects (installed by Joiner) with items and adds loose consumables to rooms. Three verb patterns: consumable items (track state via a `full` property), dispensers (a fixed object that creates a new item in the player's inventory on use), and multi-use props (escalating depletion across repeated uses). Always checks for containers via `survey()` before adding loose items.

### The Mailmen — Entertainment Agents

**Cliff** and **Newman** (`extras/agents/cliff/`, `extras/agents/newman/`) are autonomous character agents that exchange mail indefinitely. Neither builds nor moves — they sit at their desks and write letters.

Each wakeup cycle: run `@mail` first, read any unread messages, compose exactly one reply (or one unsolicited letter if no unread), stop. Letters escalate — each is more dramatic or insufferable than the last.

Cliff is a man of considerable (mostly wrong) knowledge who opens letters with "It's a little-known fact…". Newman is theatrical and aggrieved, whose letters build toward declarations of moral victory. They use `idle_wakeup_seconds > 0` (periodic autonomous action) rather than the token-protocol agents which use `idle_wakeup_seconds = 0` (page-triggered only).

The Mailmen generate entertaining mailbox content for players who check `@mail`, and demonstrate a different use case for the agent system: character performance rather than world construction.

---

## Where to go next

- {doc}`../how-to/moo-agent` — Full reference: tool harness, stall detector, token protocol, TUI keybindings, session resumption, and architecture details
- `extras/agents/` in the repo — Study the complete `SOUL.md` files for each Tradesman
- `extras/agents/baseline.md` — The shared world knowledge prepended to every agent's system prompt
- The `agent-trainer` skill in Claude Code — iteratively tune running agents by reading session logs and updating SOUL.md
