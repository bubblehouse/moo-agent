# Known Gaps

Accepted or deferred security gaps. Each entry describes the attack path, why it is accepted or deferred, and what would be required to close it. These gaps are also present as `@pytest.mark.skip` tests in the test suite.

---

## Gap 1: `dict.update()` / `dict.get()` Bypass of `_write_` and `_getitem_`

**Category**: Dunder/underscore key access

**Pass discovered**: 3 (documented), not sealed

**Attack path**:

```python
d = {}
d.update({'__class__': 'injected'})
print(d.get('__class__'))  # prints "injected"
```

`dict.update({'__class__': x})` inserts the key at C level, bypassing `_write_.__setitem__`. `dict.get()`, `dict.items()`, and `dict.values()` then return the value, bypassing `_getitem_`.

**Why not sealed**: Closing this requires subclassing `dict` to override `update`, `setdefault`, `__or__`, and `__ior__`. The `dict()` constructor and all C-level dict operations would need wrapping. This would break a significant amount of legitimate verb code that uses dicts normally.

**Risk level**: Low. Injecting `'__class__'` as a dict key does not expose any attack surface on its own. Exploitation would require passing the dict to `str.format()` (blocked) or `string.Formatter.get_field()` (module blocked).

**Test**: `test_dict_update_bypasses_write_guard` in `test_security_sandbox.py`.

---

## Gap 2: `context.caller_stack` Previous-Caller Reference

**Category**: Information disclosure

**Pass discovered**: 7 (mutation blocked by copy), disclosure aspect confirmed pass 16

**Attack path**:

```python
from moo.sdk import context
stack = context.caller_stack  # returns a copy — mutation is blocked
frame = stack[0]
prev = frame.get('previous_caller')  # live Object reference
print(prev.is_wizard())  # True if the outer caller is a wizard
```

When a wizard verb uses `set_task_perms(plain)` to run inner code as a non-wizard, `caller_stack` returns a copy of the stack (cannot be mutated), but each frame dict contains `'previous_caller'` — a live Object reference. `dict.get()` bypasses `_getitem_`, and `'previous_caller'` has no underscore prefix.

**Why not sealed**: Blocking this would require either underscore-prefixing all frame dict keys (a broad internal refactor) or replacing plain dicts with a custom read-only mapping type. The risk is information disclosure only: the non-wizard inner verb can learn whether its outer caller is a wizard. `context.caller` is a data descriptor and cannot be overwritten, so there is no privilege escalation path.

**Risk level**: Information disclosure. No privilege escalation possible.

**Test**: `test_caller_stack_previous_caller_reference_accessible` in `test_security_context.py`.

---

## Gap 3: `PeriodicTask` Returned by `invoke(periodic=True)`

**Category**: Missing permission guard on returned model instance

**Pass discovered**: 16 (documented, accepted)

**Attack path**:

A wizard calls `invoke(verb=v, delay=60, periodic=True)`, which returns a live `PeriodicTask` model instance. `PeriodicTask` has no MOO ACL guard on `.save()`. The wizard could modify `periodic_task.task` to any string.

**Why accepted**: Modifying `periodic_task.task` to an unregistered Celery task name causes `celery.exceptions.NotRegistered` at execution time — not arbitrary code execution. Only tasks decorated with `@app.task` are callable by beat. The `invoke()` wizard guard prevents non-wizards from reaching this path at all. Modifying one's own scheduled task is accepted wizard-level access.

**Risk level**: Low, within the wizard trust boundary.

**Test**: `test_invoke_periodic_returns_task_with_registered_task_name` in `test_security_context.py` (not skipped — documents the confirmation).

---

## ~~Gap 4: Coroutine `cr_frame` via `getattr()`~~ — Confirmed safe (not a gap)

**Category**: `INSPECT_ATTRIBUTES` / frame walk

**Investigation**: RestrictedPython explicitly rejects `async def` at compile time with `SyntaxError: ('Line 1: AsyncFunctionDef statements are not allowed.',)`. Coroutine objects can never be created from verb code. `cr_frame` is therefore not reachable from the sandbox — the `INSPECT_ATTRIBUTES` check in `safe_getattr` is a second-layer defence that is never reached in practice.

**Action**: Add a regression test to `test_security_builtins.py` that confirms `async def` raises `SyntaxError` (via the `TypeError` surface that `code.r_exec` exposes when compilation produces a null code object). Remove this item from the future areas checklist.

---

## Guidance for Future Auditors

When evaluating whether a gap should be sealed or accepted:

- **Privilege escalation** (non-wizard gains wizard capabilities, or ACL bypass on unowned objects): always seal.
- **Information disclosure only** (reading a value without the ability to escalate): document with `@pytest.mark.skip` and a risk boundary explanation.
- **Requires breaking legitimate verb code to fix**: document, quantify the risk, propose an alternative design path.
- **Affects wizard callers only** (wizards are trusted system administrators): document but do not treat as critical.

Always write a test even for deferred gaps — it serves as a reminder and prevents future changes from accidentally widening the gap without notice.
