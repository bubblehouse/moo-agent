# Audience Translation Rules

## Diátaxis: Where Does the Content Belong?

Before porting anything to Sphinx, decide which Diátaxis category the content fits. Content in the wrong category is the most common structural problem — gotchas end up as reference entries, conceptual explanations get buried in how-to guides.

| Category | Purpose | Hallmark | Sphinx home |
|----------|---------|---------|-------------|
| **Tutorial** | Learning by doing | Linear narrative, guided outcome | `tutorials/player-basics.md`, `tutorials/first-verb.md` |
| **How-to** | Solving a specific task | Goal-first, steps, no theory | `how-to/creating-verbs.md`, `how-to/advanced-verbs.md` |
| **Explanation** | Understanding a concept | "Why", trade-offs, context | `explanation/architecture.md`, `explanation/parser.md` |
| **Reference** | Lookup while working | Exhaustive, accurate, no narrative | `reference/verbs.md`, `reference/builtins.md`, `reference/sandbox.md` |

**Quick classification for common skill content types:**

| Content type | Diátaxis category | Likely destination |
|---|---|---|
| API name correction (`get_pobj_str` not `get_pobj_string`) | Reference | `reference/parser.md` (autosource if possible) |
| Gotcha with explanation (`return "..."` not printing) | How-to | `how-to/creating-verbs.md` |
| New SDK function | Reference | `reference/builtins.md` (autofunction) plus a one-liner in `how-to/advanced-verbs.md` |
| Parser behavior (verb search order) | Explanation + Reference | `explanation/parser.md` (concept) and `reference/parser.md` (lookup) |
| Sandbox restriction (new blocked import) | Reference | `reference/sandbox.md` (autodata if a settings constant) |
| New object class (`$furniture`) | Reference | `reference/objects.md` |
| New workflow (YAML build process) | How-to | `how-to/development.md` or `how-to/bootstrapping.md` |
| Permission semantics | Reference + How-to | `reference/permissions.md` (where each permission is enforced) and `how-to/permissions.md` (when to attempt vs. check) |

---

When porting content between layers, the facts stay the same but the framing changes significantly. The same truth reads differently for an AI agent following a task checklist versus a human developer reading documentation for the first time.

---

## Agent-Facing → Human-Facing (Skills/AGENTS.md → Sphinx)

Use this direction when porting a gotcha, correction, or API clarification from a skill or AGENTS.md into Sphinx.

**Replace WRONG/CORRECT tables with prose explanations.**

Agent facing:

```
WRONG: return "Player not found."
CORRECT: print("Player not found."); return
```

Human facing:
> Returning a string from a verb does not display it to the player. The return value is discarded by the dispatcher. Use `print()` to send output, then a bare `return` to exit early.

**Replace terse bullet rules with paragraphs that include context.**

Agent facing:

```
- obj.parents.all() required — ManyToManyField, not directly iterable
```

Human facing:
> The `parents` attribute is a Django `ManyToManyField`. Iterating it directly will raise a `TypeError`. Always call `.all()` first: `for parent in obj.parents.all()`.

**Add "why it matters."** Sphinx readers want to understand the behavior, not just avoid the trap. Explain what would go wrong without the rule.

**Remove workflow instructions.** Phase numbers, "run this next", "update memory" — none of that belongs in Sphinx. Strip it. The reader is not following a procedure.

**Add realistic verb scenarios.** An abstract rule about `get_dobj_str()` lands better when anchored to a concrete verb: a `@drop` command, a `@lock` command, something the reader can picture.

**Keep code examples but make them self-contained.** A snippet copied from a skill reference file may assume context. Expand it to a runnable minimum example.

---

## Human-Facing → Agent-Facing (Sphinx → Skills/AGENTS.md)

Less common. Use this direction when Sphinx gets a major structural update that introduces facts an AI agent needs at decision time.

**Distill prose into decision rules.** A three-paragraph Sphinx explanation becomes one bullet: the rule, when it applies, and what breaks if ignored.

**Use the `Why:` / `How to apply:` pattern for AGENTS.md corrections.**

```
Use `obj.parents.all()` to iterate parents.
Why: `parents` is a ManyToManyField — direct iteration raises TypeError.
How to apply: Any verb that loops over an object's inheritance chain.
```

**Minimize examples.** Skills assume the agent can read code. The shortest correct example that demonstrates the rule is enough.

**Remove "why it matters for beginners."** The agent knows why. Skip the orientation.

---

## Memory → Documentation Layers

Memory files (`~/.claude/projects/.../memory/`) capture ephemeral investigation results. They are not documentation. If a memory file contains a stable fact, port it.

**Port when:** The fact has been stable across multiple sessions (not a temporary workaround). The fact corrects a named API, describes a behavioral rule, or identifies a gotcha that will recur.

**Port to:** At minimum the layer most likely to surface it (skill reference file for an API correction, Sphinx for a behavioral rule). Ideally both.

**After porting:** The memory file can remain as a pointer, but should not be the only place the fact lives.

---

## Common Patterns Lost in Translation

These facts have a history of being correct in one layer but missing or wrong in another. Check these whenever doing a sync pass.

| Fact | Common gap |
|------|------------|
| `print()` output is buffered until Celery completes, arrives after PREFIX/SUFFIX | In AGENTS.md and memory; verify still present in `how-to/creating-verbs.md` |
| `return "..."` does not display to player | In verb-author skill; check `how-to/creating-verbs.md` and `how-to/advanced-verbs.md` |
| `obj.parents.all()` required for iteration | In AGENTS.md; check `reference/objects.md` |
| `get_pobj_str` not `get_pobj_string` | Now sourced from `Parser.get_pobj_str` docstring via automethod; verify nothing references the wrong name |
| `--dspec either` for optional dobj | Should be in `reference/verbs.md` dispatch metadata |
| `context.player` vs `this` when dspec is set | In `reference/parser.md` "Last match wins" and `how-to/permissions.md` caller-vs-player section |
| `lookup()` raises `NoSuchObjectError`, never returns `None` | Sourced from `moo.sdk.lookup` docstring via autofunction in `reference/builtins.md` |
| f-string / `str.format` sandbox distinction | `reference/sandbox.md` "`str.format` and `str.format_map`" |
| `line_editor=False` required for asyncssh + prompt_toolkit | `explanation/shell-internals.md` AsyncSSH Server section |
| Permissions just-attempt-it model (don't pre-check `can_caller`) | `how-to/permissions.md`; matching guidance in moo/bootstrap/AGENTS.md "Just Attempt the Operation" |
