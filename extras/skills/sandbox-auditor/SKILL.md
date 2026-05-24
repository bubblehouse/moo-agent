---
name: sandbox-auditor
description: Conduct security audits of the RestrictedPython verb sandbox. Use when asked to find sandbox escape vectors, write security tests, or seal permission gaps in the MOO verb execution environment.
compatibility: Designed for Claude Code. Requires access to the django-moo repository.
---

# Sandbox Auditor

This skill guides an agent through a systematic audit pass of the RestrictedPython-based verb sandbox in django-moo. Verb code is written by game users; the sandbox is the only barrier between their code and the host process.

## Context

The sandbox has gone through 21+ audit passes. Each pass follows the same cycle: identify a candidate attack surface, write a test that demonstrates the escape (or confirms it is blocked), then seal the hole if it is open.

See [audit-history.md](references/audit-history.md) for a complete record of all sealed holes and future areas — that file is the source of truth for pass count, vectors sealed, and per-pass focus. The six major attack categories, with full attack paths and guard mechanisms, are in [attack-categories.md](references/attack-categories.md).

## Before You Start

1. Read [audit-history.md](references/audit-history.md) — understand what has been sealed, what gaps are documented, and what is flagged for future work.
2. Read `moo/core/code.py` — `get_restricted_environment()`, `safe_getattr`, `get_protected_attribute`, `_write_`, `_getitem_`, `INSPECT_ATTRIBUTES` checks, QuerySet guard, `str.format` guard.
3. Read `moo/settings/base.py` — `ALLOWED_BUILTINS`, `ALLOWED_MODULES`, `WIZARD_ALLOWED_MODULES`, `BLOCKED_IMPORTS`.
4. Read `moo/sdk/__init__.py` — the public verb API (and the underscore aliases `_ContextManager`, `_contextmanager`, `_log` that block dangerous-name imports).
5. Scan the existing tests in `moo/core/tests/test_security_*.py` to understand what is already covered (split across `test_security_{builtins,context,imports,sandbox,queryset,random}.py` and the per-model `test_security_model_{acl,object,property,verb,mail}.py`).

Run the baseline before making any changes:

```
uv run pytest moo/core/tests/test_security_*.py -x
```

If the baseline is not green, stop and report the failures — do not audit on a broken baseline.

## Audit Workflow

### Step 1: Choose a Focus Area

Pick one focus area per audit pass. Candidates in priority order:

1. **New model additions** — any Django model added since pass 16 that does not have `save()`/`delete()` permission guards on both methods.
2. **`WIZARD_ALLOWED_MODULES` surface creep** — any new submodule exported through the wizard path that exposes mutable state, model managers, or callable chains back to framework internals.
3. **`ALLOWED_BUILTINS` return types** — for each builtin in the list, trace the type returned and check whether any returned object exposes a model manager, callable chain, or mutable global.
4. **Known gaps** — gaps documented with `@pytest.mark.skip` in the test files (see [known-gaps.md](references/known-gaps.md)).

Note: `async def` / coroutine `cr_frame` is not an active concern. RestrictedPython rejects `AsyncFunctionDef` at compile time — coroutine objects cannot be created from verb code.

### Step 2: Map the Attack Surface

For your chosen area, enumerate the objects, attributes, or import paths a verb author could reach. Ask:

- What Python objects does this path return?
- Do any of those objects have non-underscore attributes that expose a `QuerySet`, `Manager`, module reference, frame object, or callable that circumvents our guards?
- Can any format-string-style method (`format`, `format_map`, `Formatter.get_field`) be reached from this surface?
- Does the path bypass `safe_getattr` / `get_protected_attribute` entirely (e.g., via a C-level method that calls real `getattr`)?

Document your findings before writing tests.

### Step 3: Write Tests First

For each candidate vector, write a test in the appropriate file under `moo/core/tests/`:

| What you are testing | File |
|---|---|
| `_write_`, `_getitem_`, `str.format`/`format_map` guard | `test_security_sandbox.py` |
| `getattr`/`hasattr` builtins, `INSPECT_ATTRIBUTES`, dunder syntax | `test_security_builtins.py` |
| Import blocking, `BLOCKED_IMPORTS`, module traversal, return types | `test_security_imports.py` |
| `ContextManager` state, `invoke()` guards, `context.*` descriptors | `test_security_context.py` |
| `Verb`/`Property`/`Object`/`Access`/`VerbName`/`Alias` save/delete | `test_security_models.py` |
| `QuerySet`/`BaseManager` mutation and ORM surface | `test_security_queryset.py` |

See [test-patterns.md](references/test-patterns.md) for helper signatures and concrete test skeletons.

Write the test to pass when the hole is blocked and fail when it is open. Run only the security tests after each change:

```
uv run pytest moo/core/tests/test_security_*.py -x
```

### Step 4: Seal the Hole (if open)

Seal in the narrowest possible scope, in this order of preference:

1. **`moo/core/code.py`** — add a check to `safe_getattr`, `get_protected_attribute`, `_write_`, or `_getitem_`.
2. **`moo/settings/base.py`** — add to `BLOCKED_IMPORTS` or remove from `ALLOWED_BUILTINS` / `ALLOWED_MODULES`.
3. **Model `save()`/`delete()` methods** — add `can_caller()` checks in `moo/core/models/`.
4. **`moo/sdk/__init__.py`** — rename an exported name with an underscore prefix (the `_ContextManager`/`_contextmanager`/`_log` aliases are the canonical examples).

Do not add a broad block that would break legitimate verb code. Always add a "still works" regression test alongside the block test.

### Step 5: Verify No Regressions

After sealing, run the full security suite:

```
uv run pytest moo/core/tests/test_security_*.py -x
```

Then run the full test suite:

```
uv run pytest -x
```

### Step 6: Document

Update [audit-history.md](references/audit-history.md) with a new pass section:

- Pass number (increment from the last recorded pass)
- Date
- Focus area
- Vectors found (one-sentence description each)
- Vectors sealed (file and change summary)
- Any gaps not sealed (with rationale)

If a gap is real but the fix would break legitimate verb code, document it with `@pytest.mark.skip(reason="...")` in the test file and add it to [known-gaps.md](references/known-gaps.md).

Also update the project memory file if accessible:
`~/.claude/projects/-Users-philchristensen-Workspace-bubblehouse-django-moo/memory/project_security_audit.md`

## What Good Tests Look Like

Each test must have a docstring explaining:

1. The attack path (how an attacker reaches the vulnerable attribute or method)
2. Why the naive code would fail without the guard
3. What mechanism blocks it (`INSPECT_ATTRIBUTES`, `_QUERYSET_ALLOWED`, `BLOCKED_IMPORTS`, etc.)

Tests confirming confirmed-safe behaviour should include the specific reason the vector is not exploitable.

## Reference Files

- [audit-history.md](references/audit-history.md) — all 50 sealed holes by pass, known gaps, and future areas
- [attack-categories.md](references/attack-categories.md) — the six major attack categories with attack paths and guard mechanisms
- [test-patterns.md](references/test-patterns.md) — test helpers, skeletons for each test type, and common assertion patterns
- [known-gaps.md](references/known-gaps.md) — accepted and deferred gaps with risk levels and rationale
