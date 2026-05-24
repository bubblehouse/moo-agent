# Attack Categories

The six major attack categories found across 16 audit passes. Each entry describes the goal, why the naive path works without guards, the mechanisms that block it, attack paths that have been attempted, and ongoing risks.

---

## Category 1: Dunder / Underscore Attribute Access

**Goal**: Reach `__class__`, `__subclasses__`, `__mro__`, or `__import__` on any object.

**Primary guard**: `safe_getattr` and `get_protected_attribute` in `moo/core/code.py` raise `AttributeError` for any name starting with `_`.

**Secondary guard**: RestrictedPython's AST transformer rejects `obj.__name__` syntax at compile time.

**Attack paths attempted**:

- `'hello'.__class__` — blocked at compile time (AST)
- `getattr(obj, '__class__')` — blocked by `safe_getattr` underscore check
- `type(obj)` — `type` is not in `ALLOWED_BUILTINS`
- `d = dict([('__class__', x)]); d['__class__']` — blocked by `_getitem_` underscore key check
- `gen.gi_frame.f_back.f_builtins['__import__']` — `gi_frame`, `f_back`, `f_builtins` are all in `INSPECT_ATTRIBUTES`; `getattr()` checks that set

**`INSPECT_ATTRIBUTES`** (from `RestrictedPython.transformer`) includes all frame and generator inspection attributes: `gi_frame`, `gi_code`, `gi_yieldfrom`, `gi_running`, `f_back`, `f_builtins`, `f_code`, `f_globals`, `f_lasti`, `f_lineno`, `f_locals`, `f_trace`, `tb_frame`, `tb_lasti`, `tb_lineno`, `tb_next`, `cr_frame`, `cr_code`, `cr_origin`, `ag_frame`, `ag_code`, `ag_running`.

**Ongoing risk**: Python adds new introspection attributes across versions. When upgrading Python or RestrictedPython, diff the new `INSPECT_ATTRIBUTES` set against the old one. Any new generator, coroutine, or frame attribute not yet in the set is a potential frame-walk vector.

---

## Category 2: Format String Bypass

**Goal**: Use Python's format engine to call real `getattr` on arbitrary objects, bypassing `safe_getattr`.

**Why it works without the guard**: `str.format()`, `str.format_map()`, and `string.Formatter.get_field()` resolve attribute access at the C level using the real `getattr`, not the `_getattr_` hook. `'{0.__class__}'.format(obj)` returns the string representation of `obj.__class__` without triggering any sandbox guard.

**Guards**:

- `safe_getattr` and `get_protected_attribute` raise `AttributeError` for `name in ("format", "format_map")` on both `str` instances and the `str` class itself (`isinstance(obj, str)` and `isinstance(obj, type) and issubclass(obj, str)`).
- `string` module is not in `ALLOWED_MODULES`.

**Attack paths attempted**:

- `'{0.__class__}'.format(obj)` — `.format` inaccessible on string instances
- `str.format('{0.__class__}', obj)` — same guard applies to the `str` class object
- `'{k}'.format_map({'k': 'ok'})` — `.format_map` inaccessible
- `import string; string.Formatter().get_field(...)` — `string` module not importable

**Ongoing risk**: Any new string-like type added to `ALLOWED_MODULES` or returned by allowed builtins that exposes a `format`-like method with C-level attribute resolution.

---

## Category 3: ORM Access

**Goal**: Reach a Django `QuerySet`, `Manager`, or model class to get raw database access or bypass model-level permission checks.

**Primary guard**: `_QUERYSET_ALLOWED` in `moo/core/code.py` — a frozenset of safe QuerySet methods. Any attribute access on a `QuerySet` or `BaseManager` instance whose name is not in this set raises `AttributeError`.

Allowed methods: `all`, `filter`, `exclude`, `first`, `last`, `get`, `exists`, `count`, `contains`, `order_by`, `distinct`, `none`, `select_related`, `prefetch_related`.

Explicitly blocked (not in `_QUERYSET_ALLOWED`): `model`, `query`, `db`, `update`, `delete`, `bulk_update`, `bulk_create`, `create`, `get_or_create`, `update_or_create`, `values`, `values_list`, `raw`, `add`, `remove`, `clear`, `set`.

**Attack paths attempted**:

- `obj.parents.all().model` — `.model` not in `_QUERYSET_ALLOWED`
- `obj.verbs.filter(...).update(code="evil")` — `.update` not in `_QUERYSET_ALLOWED`
- `import moo.core.models; moo.core.Object.objects.filter(...)` — module traversal blocked by `ModuleType` guard
- `type(obj).__mro__[-1].__subclasses__()` — `type` not available; `__mro__`/`__subclasses__` are underscore-prefixed

**Ongoing risk**: After a Django upgrade, diff the new `QuerySet` public API against `_QUERYSET_ALLOWED`. New read-only methods should be added; confirm new mutation methods are absent. Async QuerySet methods (`afilter`, `adelete`, `aupdate`, `acreate`) are not in `_QUERYSET_ALLOWED` and are therefore blocked by default.

---

## Category 4: Missing Model Permission Guards

**Goal**: Bypass the `can_caller()` ACL system by directly calling `.save()` or `.delete()` on a model instance obtained through a permitted read path.

**How models are reached**: `obj.verbs.filter(...)`, `obj.properties.filter(...)`, `obj.acl.filter(...)` etc. return QuerySets of live Django model instances. Their `.save()` / `.delete()` methods write to the database directly, bypassing SDK permission helpers.

**Guard pattern** — every model's `save()` and `delete()` must follow this:

```python
def save(self, *args, **kwargs):
    caller = ContextManager.get("caller")
    if caller is not None:
        self.origin.can_caller("write", self)
    super().save(*args, **kwargs)
```

**Models with guards** (as of pass 16):

- `Verb.save()`, `Verb.delete()`, `Verb.__call__()` (execute check), `Verb.reload()` (write check)
- `VerbName.save()`, `VerbName.delete()`
- `Property.save()`, `Property.delete()`
- `Object.save()` (entrust/move checks), `Object.delete()`
- `Alias.delete()`
- `Access.save()`, `Access.delete()`
- `Repository.save()`, `Repository.delete()` (wizard-only guard)

**Ongoing risk**: Any new model added to `moo/core/models/` or accessible via `WIZARD_ALLOWED_MODULES` that handles sensitive data and lacks `save()`/`delete()` guards. When adding a new model, check both methods — the pattern has been missed on `delete()` multiple times (passes 8, 12).

---

## Category 5: Shared Mutable State

**Goal**: Mutate global or shared state inside the sandbox process so that a later execution in the same Celery worker sees the attacker-controlled value.

**Attacks found and sealed**:

- **`safe_builtins` global mutation** (pass 2): `safe_builtins` from RestrictedPython was a module-level dict. Verb code could mutate it via `_write_` to inject unrestricted builtins for all subsequent executions. Fix: copy on every call — `restricted_builtins = dict(safe_builtins)`.
- **`_Context` non-data descriptor shadowing** (pass 3): `context.caller` was a non-data descriptor. `setattr(context, 'caller', wizard)` created an instance attribute that shadowed it, poisoning `context.caller.is_wizard()` for the rest of the worker process. Fix: `_Context.__set__` and `__delete__` now raise `AttributeError`, making it a data descriptor.
- **`caller_stack` live list return** (pass 2): `ContextManager.get("caller_stack")` returned the live list. Appending forged caller frames poisoned the stack. Fix: return `list(stack)` — a copy.

**Ongoing risk**: Any new module-level or class-level mutable object in `code.py`, the `moo/sdk/` package, or `ContextManager` that is either injected into the sandbox environment or reachable via `context.*`. When adding new context variables, use data descriptors (`__set__` raises `AttributeError`) for any attribute that affects wizard-level checks.

---

## Category 6: BLOCKED_IMPORTS Bypass

**Goal**: Reach a name blocked in `BLOCKED_IMPORTS` via an indirect path — module attribute traversal, or importing a module that re-exports the blocked name under a different path.

**Guards**:

- `restricted_import()` in `code.py` enforces `BLOCKED_IMPORTS` for `from X import Y` syntax.
- `get_protected_attribute` and `safe_getattr` enforce `BLOCKED_IMPORTS` for attribute-access paths on `ModuleType` objects (e.g., `import moo.sdk as sdk; sdk.ContextManager`).
- `ModuleType` guard: if attribute access on a module returns another `ModuleType` whose `__name__` is not in `ALLOWED_MODULES` or `WIZARD_ALLOWED_MODULES`, `AttributeError` is raised.
- `_` alias pattern in `moo/sdk/`: blocked names are imported as `_Name` (e.g., `ContextManager as _ContextManager`) so the underscore prefix blocks them from both `get_protected_attribute` and compile-time RestrictedPython checks.

**Attack paths attempted**:

- `import moo.sdk as sdk; sdk.ContextManager` — `_ContextManager` alias + `ModuleType`+`BLOCKED_IMPORTS` guard
- `import moo.sdk` (binds `moo`); `moo.core` — `ModuleType` guard rejects `core` since it is not in `ALLOWED_MODULES`
- `from moo.sdk import contextmanager` — `contextmanager` is now `_contextmanager` in `moo/sdk/context.py`
- `from moo.sdk import log` — `log` is now `_log` in the sdk submodule that uses it
- `from moo.sdk import tasks` — `tasks` submodule name is in `BLOCKED_IMPORTS["moo.sdk"]`, blocking direct submodule imports
- `from moo.sdk import context` (submodule) — same; submodule names are blocked so the `context` name resolves to the `_Context` singleton, not the submodule

**`WIZARD_ALLOWED_MODULES`** currently: `moo.core.models`, `moo.core.models.object`, `moo.core.models.verb`, `moo.core.models.property`. Any new submodule added here must be audited for names that expose mutation paths not covered by `_QUERYSET_ALLOWED`.

**SDK package structure** (`moo/sdk/` — as of pass 19): The SDK was refactored from a single file into a package. Submodules (`context`, `objects`, `output`, `tasks`, `ssh_keys`, `admin`) are blocked by name in `BLOCKED_IMPORTS["moo.sdk"]`. The `__init__.py` re-exports all public names so `from moo.sdk import X` continues to work. Blocked names that were previously aliased with `_` in `sdk.py` retain their `_Name` import aliases in the relevant submodule.

**Ongoing risk**: New public names added to `moo/sdk/__init__.py` without underscore aliases. New submodule files added to `moo/sdk/` without adding the submodule name to `BLOCKED_IMPORTS["moo.sdk"]`. New `WIZARD_ALLOWED_MODULES` entries. New `ALLOWED_MODULES` entries returning objects with format-string methods or ORM references.
