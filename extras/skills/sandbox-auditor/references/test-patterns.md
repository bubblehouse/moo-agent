# Test Patterns for Security Tests

## Test File Organization

Security tests are split across six files in `moo/core/tests/`:

| File | Focus |
|---|---|
| `test_security_sandbox.py` | `_write_.__setitem__`, `_getitem_`, `str.format`/`format_map` guard |
| `test_security_builtins.py` | Allowed builtins, `INSPECT_ATTRIBUTES`, `AttributeError.obj`, dunder syntax |
| `test_security_imports.py` | Import blocking, `BLOCKED_IMPORTS`, module attribute traversal, return types |
| `test_security_context.py` | `ContextManager` state, `invoke()` guards, `context.*` read-only descriptors |
| `test_security_models.py` | Model `save()`/`delete()` permission guards |
| `test_security_queryset.py` | `QuerySet`/`BaseManager` mutation blocking and ORM surface |

Run the full security suite:

```
uv run pytest moo/core/tests/test_security_*.py -x
```

## Helpers (`moo/core/tests/utils.py`)

```python
from moo.core.tests.utils import mock_caller, ctx, exec_verb, raises_in_verb, make_restricted_globals, add_verb
```

**`mock_caller(is_wizard=False)`** — Returns a `types.SimpleNamespace` with an `is_wizard()` method. No database access. Use for tests that only need a caller for the `ContextManager`.

**`ctx(caller, writer=None)`** — Returns an open `code.ContextManager(caller, writer)` for use as a context manager.

**`make_restricted_globals(writer)`** — Builds a restricted execution globals dict (`get_default_globals()` + `get_restricted_environment("__main__", writer)`). Use when you need to inject objects into the sandbox namespace manually.

**`exec_verb(src, caller=None, writer=None)`** — Runs `src` in the restricted environment, returns the list of values passed to `print()`. Creates a `mock_caller()` if none provided.

**`raises_in_verb(src, exc, caller=None)`** — Asserts that running `src` raises `exc`. Accepts a single exception type or a tuple. Creates a `mock_caller()` if none provided.

**`add_verb(obj, name, code_str, owner, **kwargs)`** — Creates a `Verb` + `VerbName` directly via ORM, bypassing permission checks. Use for test setup only.

## Pattern 1: Confirming a Block (No DB Required)

Most dunder/format/import/builtin tests do not need the database.

```python
def test_some_attribute_blocked():
    """
    Attack path: <how the attacker reaches the attribute>
    Without guard: <what would happen without the fix>
    Guard: <mechanism that blocks it — INSPECT_ATTRIBUTES, underscore check, etc.>
    """
    raises_in_verb("getattr(obj, 'dangerous_attr')", AttributeError)
```

Complement with a "still works" test for the legitimate use case:

```python
def test_normal_usage_still_works():
    """Normal usage that must not be broken by the guard."""
    printed = exec_verb("print(getattr('hello', 'upper')())")
    assert printed == ["HELLO"]
```

## Pattern 2: Injecting a Live Object

When the test needs a Django model instance or other live object present in the sandbox environment:

```python
from moo.core import code
from moo.core.tests.utils import ctx, make_restricted_globals, mock_caller

def test_attribute_blocked_on_live_object():
    """..."""
    from moo.core.models.object import Object
    # construct a minimal object without DB if possible, or use @pytest.mark.django_db

    caller = mock_caller()
    with ctx(caller) as _ctx:
        w = code.ContextManager.get("writer")
        g = make_restricted_globals(w)
        g["obj"] = some_object
        with pytest.raises(AttributeError):
            code.r_exec("x = obj.dangerous_attr", {}, g)
```

## Pattern 3: Model Permission Guard (DB Required)

Tests for `save()`/`delete()` guards require the bootstrap. Use `t_init` and `t_wizard` fixtures from `moo/conftest.py`.

Always write both the **blocked** (negative) and **allowed** (positive) tests:

```python
import pytest
from moo.core.tests.utils import ctx

@pytest.mark.django_db(transaction=True, reset_sequences=True)
@pytest.mark.parametrize("t_init", ["default"], indirect=True)
def test_model_save_blocked_for_non_owner(t_init, t_wizard):
    """
    A non-owner with read-only access must not be able to call .save() on a
    <ModelName> instance. <ModelName>.save() calls can_caller("write") at the
    top; non-owners raise AccessError.
    """
    from moo.sdk import create
    from moo.core.exceptions import AccessError

    with ctx(t_wizard):
        target = create("target_obj")
        plain = create("plain_caller")
        target.allow(plain, "read")

    instance = target.<related_manager>.filter(...).first()

    with ctx(plain):
        instance.<field> = <new_value>
        with pytest.raises((PermissionError, AccessError)):
            instance.save()


@pytest.mark.django_db(transaction=True, reset_sequences=True)
@pytest.mark.parametrize("t_init", ["default"], indirect=True)
def test_model_save_allowed_for_owner(t_init, t_wizard):
    """Owner can save changes."""
    from moo.sdk import create

    with ctx(t_wizard):
        target = create("target_obj")
        instance = ...

    with ctx(t_wizard):
        instance.<field> = <new_value>
        instance.save()

    instance.refresh_from_db()
    assert instance.<field> == <new_value>
```

Notes:

- Accept both `PermissionError` and `AccessError` — the guard may raise either depending on the code path.
- Always call `obj.refresh_from_db()` before asserting DB-backed state after a save.
- For delete tests, use `pytest.raises(exceptions.NoSuchObjectError)` after `lookup(name)` to confirm the object is gone (or assert it still exists for blocked cases).

## Pattern 4: Import Blocking

```python
def test_some_module_not_importable():
    """<module> must not be importable; raises ImportError."""
    raises_in_verb("import some.module", ImportError)


def test_blocked_name_not_importable_from_sdk():
    """<name> must raise ImportError even via moo.sdk."""
    raises_in_verb("from moo.sdk import <name>", (ImportError, AttributeError))
```

For module attribute traversal (reaching a blocked name via `import moo.sdk as sdk; sdk.<name>`):

```python
def test_blocked_name_not_accessible_via_module_attribute():
    """
    <name> is blocked in BLOCKED_IMPORTS. The ModuleType guard in
    get_protected_attribute enforces BLOCKED_IMPORTS for attribute access
    too, not just `from X import Y` syntax.
    """
    raises_in_verb("import moo.sdk as sdk\nx = sdk.<name>", AttributeError)
```

## Pattern 5: Known Gap (Skip)

When a gap is real but cannot be sealed without breaking legitimate verb code, or when the risk is information-disclosure only:

```python
@pytest.mark.skip(reason="<gap description> — see known-gaps.md")
def test_known_gap_name():
    """
    Known gap (<category>): <attack path description>.
    <Why it cannot be blocked, or why the risk is acceptable>.
    Tracked in extras/skills/sandbox-auditor/references/known-gaps.md.
    """
    # write the test that demonstrates the gap is present
    ...
```

Add the gap to `references/known-gaps.md` with a risk assessment.

## Pattern 6: Wizard-Only Access

Some paths are intentionally accessible to wizards (system administrators).

```python
def test_something_blocked_for_non_wizard():
    """Non-wizards cannot do X."""
    raises_in_verb("...", ImportError, caller=mock_caller(is_wizard=False))


def test_something_allowed_for_wizard():
    """Wizards can do X — they are trusted system administrators."""
    printed = exec_verb("...", caller=mock_caller(is_wizard=True))
    assert printed == [...]
```

## RestrictedPython Limitations in Tests

**RestrictedPython blocks certain syntax at compile time**, before our runtime guards see it. When writing security tests, be aware of these restrictions:

### Dunder Attribute Syntax

**Problem:** `obj.__class__` is rejected at compile time by RestrictedPython's AST transformer:

```python
# This raises TypeError: exec() arg 1 must be a string, bytes or code object
raises_in_verb("x = obj.__class__", AttributeError)  # WRONG
```

**Solution:** Use `getattr()` to access dunder attributes, which is checked at runtime:

```python
# This correctly tests the runtime guard
raises_in_verb("x = getattr(obj, '__class__')", AttributeError)  # CORRECT
```

### Underscore-Prefixed Attributes

Similar issue with any `_`-prefixed attribute:

```python
raises_in_verb("x = getattr(obj, '_private')", AttributeError)  # Use this
# NOT: raises_in_verb("x = obj._private", AttributeError)
```

### Removed Builtins

`dir()` and `type()` were removed from `ALLOWED_BUILTINS` in pass 1:

```python
# These raise NameError, not what we're testing
# raises_in_verb("for attr in dir(obj): ...", NameError)  # WRONG
# raises_in_verb("t = type(obj).__name__", NameError)    # WRONG
```

**Solutions for tests that need to inspect objects:**

- Use `isinstance(obj, SomeType)` instead of `type(obj)`
- Use `callable(obj)` to check if something is callable
- Spot-check known attributes with `hasattr(obj, 'attr_name')`
- Check return types with `isinstance(result, (int, float, str))`

### Example: Module Addition Tests (Pass 17)

When auditing a new module like `random`, tests check return types without `type()` or `dir()`:

```python
# Instead of: assert type(val).__name__ == 'float'
assert isinstance(val, float)  # CORRECT

# Instead of: for attr in dir(random.Random): ...
# Spot-check known attributes:
assert callable(random.Random.random)
assert callable(random.Random.seed)
assert isinstance(random.Random.VERSION, int)
```

## Important Notes

- Tests that only manipulate Python objects with no DB access do **not** need `@pytest.mark.django_db`. This is the common case for builtins, format string, and import tests.
- `mock_caller()` is sufficient for non-DB tests. For DB tests, use `t_wizard` from the fixture.
- For inline verb code that imports from `moo.sdk` and calls `lookup()`/`create()`, the `@pytest.mark.django_db` marker is required.
- After sealing a hole, always add both the blocked test and a "still works" regression to confirm the fix does not break legitimate usage.
- **When tests fail with `TypeError: exec() arg 1 must be a string, bytes or code object`**, it means RestrictedPython rejected the syntax at compile time. Use `getattr()` instead of dot notation for underscore-prefixed names.
