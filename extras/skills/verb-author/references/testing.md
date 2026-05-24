# Testing Verbs

## Two Test Types

**Core unit tests** (`moo/core/tests/`) — test models and the execution engine without bootstrapping the full game world.

**Bootstrap integration tests** (`moo/bootstrap/default/verbs/tests/`) — test verbs against the fully initialised `default` world. Write these when adding or changing a `default/verbs/` verb.

## Bootstrap Test Skeleton

```python
import pytest

from moo.core import code, parse
from moo.sdk import create, lookup
from moo.core.models import Object


@pytest.mark.django_db(transaction=True, reset_sequences=True)
@pytest.mark.parametrize("t_init", ["default"], indirect=True)
def test_my_verb(t_init: Object, t_wizard: Object):
    printed = []

    def _writer(msg):
        printed.append(msg)

    with code.ContextManager(t_wizard, _writer) as ctx:
        system = lookup(1)
        lab = t_wizard.location

        # Set up objects
        widget = create("widget", parents=[system.thing], location=t_wizard)

        # Run the command
        parse.interpret(ctx, "drop widget")

        # Assert DB state
        widget.refresh_from_db()
        assert widget.location == lab

    # Assert console output
    assert printed == ["You drop widget."]
```

## Fixtures

Both fixtures come from `moo/conftest.py`:

- **`t_init`** — bootstraps the `default/` package and yields the system object (#1). Must be requested via `@pytest.mark.parametrize("t_init", ["default"], indirect=True)`.
- **`t_wizard`** — returns the Wizard player Object. Wizard starts in The Laboratory.

The `t_wizard` fixture is available in all bootstrap tests without extra parametrize calls.

## ContextManager

`code.ContextManager(player, writer)` sets up the execution context for verb code. It must wrap all verb calls and `parse.interpret` calls.

```python
printed = []

with code.ContextManager(t_wizard, printed.append) as ctx:
    parse.interpret(ctx, "take widget")
```

The `writer` callable receives everything `print()` sends to the player during the context.

For tests that don't care about output:

```python
with code.ContextManager(t_wizard, lambda msg: None) as ctx:
    parse.interpret(ctx, "look")
```

## Asserting Database State

Always call `refresh_from_db()` before asserting locations, properties, or other DB-backed fields after a `parse.interpret` or verb call:

```python
widget.refresh_from_db()
assert widget.location == lab
```

## Capturing `write()` Output

`write(obj, msg)` (low-level, bypasses filtering) emits `RuntimeWarning` in the test environment instead of writing to a real connection. Capture these with `pytest.warns`:

```python
with pytest.warns(RuntimeWarning, match=r"ConnectionError") as warnings:
    parse.interpret(ctx, "say Hello there!")

messages = [str(w.message) for w in warnings.list]
assert any("(Wizard)): You: Hello there!" in m for m in messages)
assert any("(Player)): Wizard: Hello there!" in m for m in messages)
```

The warning format is: `ConnectionError(#<pk> (<name>)): <message>`

## Direct Verb Calls

Inside a `ContextManager`, verbs are callable as Python methods without going through the parser. Useful for testing helper and message verbs:

```python
with code.ContextManager(t_wizard, _writer):
    system = lookup(1)
    widget = create("widget", parents=[system.thing], location=t_wizard)

    assert widget.take_succeeded_msg() == f"You take {widget.title()}."
    assert widget.take_failed_msg() == "You can't pick that up."
    assert widget.drop_succeeded_msg() == f"You drop {widget.title()}."
```

## Inline Verb Tests

For quick isolated tests without the full bootstrap:

```python
@pytest.mark.django_db(transaction=True, reset_sequences=True)
@pytest.mark.parametrize("t_init", ["default"], indirect=True)
def test_inline_verb(t_init: Object, t_wizard: Object):
    with code.ContextManager(t_wizard, lambda msg: None):
        obj = create("Test Object")
        obj.add_verb("my_verb", code='return "Hello"')
        result = obj.invoke_verb("my_verb")
        assert result == "Hello"
```

## Testing Locks

Set a `key` property on a destination to block specific objects:

```python
# Block widget specifically
destination.set_property("key", ["!", widget.id])
widget.moveto(destination)
widget.refresh_from_db()
assert widget.location != destination  # blocked

# key = None means unlocked (the default)
destination.set_property("key", None)
widget.moveto(destination)
widget.refresh_from_db()
assert widget.location == destination  # allowed
```

## Testing Deletion

`lookup()` raises `NoSuchObjectError`, never returns `None`. Test that an object was deleted:

```python
from moo.core import exceptions

with pytest.raises(exceptions.NoSuchObjectError):
    lookup("deleted widget")
```

## Multi-Player Tests

The `default` bootstrap creates two objects: Wizard and Player (an NPC with no Django User). Both start in The Laboratory. To test interactions between them:

```python
with code.ContextManager(t_wizard, _writer) as ctx:
    player = lookup("Player")
    player.location = t_wizard.location
    player.save()

    with pytest.warns(RuntimeWarning, match=r"ConnectionError") as w:
        parse.interpret(ctx, "say Hello!")

    messages = [str(x.message) for x in w.list]
    assert any("(Player)): Wizard: Hello!" in m for m in messages)
```

## Useful Imports for Test Files

```python
import pytest

from moo.core import code, parse
from moo.core import exceptions
from moo.sdk import create, lookup
from moo.core.models import Object
```
