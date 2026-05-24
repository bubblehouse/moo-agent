# sandbox-auditor

A Claude Code skill for conducting systematic security audits of the RestrictedPython verb sandbox in django-moo.

## When to use it

Invoke this skill when you want to:

- Find sandbox escape vectors in the verb execution environment
- Write security tests for a suspected attack surface
- Seal a known permission gap
- Do a general security audit pass after adding new models, modules, or builtins

Trigger phrases: "find sandbox escape vectors", "write security tests", "audit the verb sandbox", "seal permission gaps".

## How to invoke

```
/sandbox-auditor
/sandbox-auditor audit new model additions since last pass
/sandbox-auditor check whether $string_utils exposes anything dangerous
```

## Context

Verb code is written by game users. The RestrictedPython sandbox is the only barrier between their code and the host process. The sandbox has gone through 17 audit passes with 50 vectors sealed across 630+ tests.

## What it does

The skill guides a single audit pass through six steps:

1. **Choose a focus area** — new model additions, `WIZARD_ALLOWED_MODULES` surface creep, `ALLOWED_BUILTINS` return types, or documented known gaps
2. **Map the attack surface** — enumerate what objects, attributes, and import paths are reachable from the chosen area
3. **Write tests first** — one test per candidate vector, written to pass when blocked and fail when open
4. **Seal the hole** — narrowest possible fix in `moo/core/code.py`, `moo/settings/base.py`, model `save()`/`delete()` guards, or `moo/sdk.py`
5. **Verify no regressions** — run the full security suite, then the full test suite
6. **Document** — update `audit-history.md` with the pass record

## Key files in the codebase

| File | Role |
|------|------|
| `moo/core/code.py` | Sandbox implementation: `get_restricted_environment()`, `safe_getattr`, guards |
| `moo/settings/base.py` | `ALLOWED_BUILTINS`, `ALLOWED_MODULES`, `WIZARD_ALLOWED_MODULES`, `BLOCKED_IMPORTS` |
| `moo/sdk.py` | Public verb API |
| `moo/core/tests/test_security_*.py` | All security tests (130 tests, 6 files) |

## Reference files

| File | Contents |
|------|----------|
| `references/audit-history.md` | All 50 sealed holes by pass, known gaps, and future areas |
| `references/attack-categories.md` | Six major attack categories with attack paths and guard mechanisms |
| `references/test-patterns.md` | Test helpers, skeletons for each test type, assertion patterns |
| `references/known-gaps.md` | Accepted and deferred gaps with risk levels and rationale |
