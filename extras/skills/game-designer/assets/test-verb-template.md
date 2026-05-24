# `@test-<name>` Verb Template

Place this verb on `$programmer` so any programmer can run it:

```
@edit verb test-<name> on "$programmer"
```

Then paste the code below, replacing all `# TODO` placeholders.

## Important Limitations

**Very Long Code Warning**: When test verbs exceed ~100 lines, creating them via `@edit verb ... with "..."` can fail with compilation errors in RestrictedPython's execution context. The verb gets stored correctly but fails to run.

**Workarounds**:

1. **Simplify the test**: Use a dictionary-based approach instead of nested functions and reduce formatting:

   ```python
   results = {"passed": 0, "failed": 0}
   # ... inline pass/fail logic without helper functions ...
   ```

2. **Use the interactive editor**: Run `@edit verb test-<name> on "$programmer"` without `with`, then paste the full code in the editor
3. **Create via multiple @eval chunks**: Break the verb into smaller sections and concatenate

**Invocation**: Test verbs are in-world verbs, not administrative commands. Run them **without** the `@` prefix: `test-moes-tavern`, not `@test-moes-tavern`.

---

## Full Template

```python
from moo.sdk import lookup, NoSuchObjectError, NoSuchVerbError

passed = 0
failed = 0

def ok(label):
    global passed
    passed += 1
    print(f"[green]PASS[/green] {label}")

def fail(label, reason=""):
    global failed
    failed += 1
    suffix = f": {reason}" if reason else ""
    print(f"[red]FAIL[/red] {label}{suffix}")

print("[bold]--- Room checks ---[/bold]")

# TODO: Add one block per expected room.
# Pattern: lookup by exact name, PASS if found, FAIL with reason if not.

try:
    main_room = lookup("TODO: Main Room Name")
    ok("Main Room exists")
except NoSuchObjectError as e:
    main_room = None
    fail("Main Room exists", str(e))

try:
    second_room = lookup("TODO: Second Room Name")
    ok("Second Room exists")
except NoSuchObjectError as e:
    second_room = None
    fail("Second Room exists", str(e))

# ... repeat for all rooms ...


print("[bold]--- Exit checks ---[/bold]")

# TODO: For each expected exit, check that the exit's dest matches the expected room.
# Pattern: iterate room.exits.all(), match by direction alias or name, check dest.

if main_room:
    found_north = False
    for exit_obj in main_room.exits.all():
        try:
            dest = exit_obj.get_property("dest")
            if second_room and dest.id == second_room.id:
                found_north = True
                break
        except Exception:
            pass
    if found_north:
        ok("Main Room -> north -> Second Room")
    else:
        fail("Main Room -> north -> Second Room", "exit or dest not found")

# ... repeat for all exit pairs ...


print("[bold]--- Object checks ---[/bold]")

# TODO: For each expected object in each room, check that it's present in contents.
# Pattern: iterate room.contents.all(), match by name substring or exact name.

if main_room:
    names_in_main = [o.name for o in main_room.contents.all()]
    target = "TODO: object name"
    if any(target.lower() in n.lower() for n in names_in_main):
        ok(f"'{target}' in Main Room")
    else:
        fail(f"'{target}' in Main Room", f"found: {names_in_main}")

# ... repeat for all expected objects ...


print("[bold]--- NPC checks ---[/bold]")

# TODO: For each NPC, check presence and that the speak verb exists.
# Pattern: lookup NPC by name, check location, check get_verb("speak").

try:
    npc = lookup("TODO: NPC Name")
    ok("NPC exists")
    try:
        npc.get_verb("speak")
        ok("NPC has speak verb")
    except NoSuchVerbError:
        fail("NPC has speak verb", "NoSuchVerbError")
    except Exception as e:
        fail("NPC has speak verb", str(e))
except NoSuchObjectError as e:
    fail("NPC exists", str(e))

# ... repeat for all NPCs ...


print("[bold]--- Verb checks ---[/bold]")

# TODO: For each parent class, check that key verbs exist.
# Pattern: lookup class by name, call get_verb, PASS/FAIL.

try:
    glass_class = lookup("TODO: Generic Class Name")
    try:
        glass_class.get_verb("TODO: verb name")
        ok("Generic Class has 'verb' verb")
    except NoSuchVerbError:
        fail("Generic Class has 'verb' verb", "NoSuchVerbError")
    except Exception as e:
        fail("Generic Class has 'verb' verb", str(e))
except NoSuchObjectError as e:
    fail("Generic Class exists", str(e))

# ... repeat for all parent classes and their key verbs ...


print(f"[bold]{passed}/{passed+failed} checks passed.[/bold]")
```

---

## Simplified Template (No Nested Functions)

Use this version if the standard template causes compilation errors:

```python
from moo.sdk import lookup, NoSuchObjectError, NoSuchVerbError

results = {"passed": 0, "failed": 0}

print("[bold]--- Room checks ---[/bold]")

# TODO: Check each room
try:
    main_room = lookup("TODO: Main Room Name")
    results["passed"] += 1
    print(f"[green]PASS[/green] Main Room exists")
except NoSuchObjectError as e:
    main_room = None
    results["failed"] += 1
    print(f"[red]FAIL[/red] Main Room exists: {e}")

# ... repeat for all rooms ...

print("[bold]--- Object checks ---[/bold]")

# TODO: Check objects in each room
if main_room:
    names = [o.name for o in main_room.contents.all()]
    target = "TODO: object name"
    if any(target.lower() in n.lower() for n in names):
        results["passed"] += 1
        print(f"[green]PASS[/green] Main Room: {target}")
    else:
        results["failed"] += 1
        print(f"[red]FAIL[/red] Main Room: {target} (not in {names})")

# ... repeat for all objects ...

print("[bold]--- Verb checks ---[/bold]")

# TODO: Check verbs on objects
try:
    obj = lookup("TODO: object name")
    obj.get_verb("TODO: verb name")
    results["passed"] += 1
    print(f"[green]PASS[/green] object: verb")
except NoSuchObjectError as e:
    results["failed"] += 1
    print(f"[red]FAIL[/red] object: verb (object not found: {e})")
except NoSuchVerbError:
    results["failed"] += 1
    print(f"[red]FAIL[/red] object: verb (verb not found)")

# ... repeat for all verb checks ...

total = results["passed"] + results["failed"]
print(f"[bold]{results['passed']}/{total} checks passed.[/bold]")
```

This version uses a dictionary for counters instead of nested functions with `global`, which avoids RestrictedPython's limitations with nested function scopes.

---

## Usage Notes

- All room lookups use `lookup()`, which raises `NoSuchObjectError` if not found.
- Store room objects in local variables so exit and contents checks can reference them.
- Use `room.exits.all()` to iterate exits; check `exit_obj.get_property("dest")` for connectivity.
- Use `room.contents.all()` for object presence; match names with `in` for substring matching.
- Use broad `except Exception` for verb/property checks — the specific exception type doesn't matter for the test output.
- Rich markup (`[green]`, `[red]`, `[bold]`) renders in the MOO terminal.
- Final summary line format: `N/N checks passed.`
- The total count includes both passed and failed: `passed + failed`.
