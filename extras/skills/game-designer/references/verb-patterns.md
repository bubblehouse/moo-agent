# Verb Code Patterns

All verbs run inside the RestrictedPython sandbox.

**No shebang in SSH-edited verbs.** The `#!moo verb name --on $obj` shebang is only for bootstrap verb *files* in `moo/bootstrap/default/verbs/`. When you create a verb via `@edit verb <name> on "<obj>"` in an SSH session, the verb name and target are already registered by that command — the code body starts directly with imports.

## Imports

```python
from moo.sdk import context, create, lookup, invoke
from moo.sdk import NoSuchObjectError, NoSuchVerbError, NoSuchPropertyError
import random
import time
```

Available restricted imports: `moo.sdk`, `re`, `datetime`, `time`, `hashlib`, `random`

## Output

```python
# Send text to the calling player
print("You do the thing.")

# Announce to everyone in the room except the caller
context.player.location.announce_all_but(context.player, "Someone does the thing.")

# Announce to everyone in the room except the caller (shorter form, excludes context.player implicitly)
context.player.location.announce("Someone does the thing.")

# Announce to everyone including the caller
context.player.location.announce_all("A thing happens.")
```

Never use `return "message"` — returned values are not displayed. Use `print()` for player-visible output and bare `return` for early exit.

## Sittable Objects — Use `$furniture`

For any object a player can sit on (chair, bench, couch, crate, boulder), use `$furniture` as the parent instead of `$thing`. It provides `sit`/`stand` verbs automatically, tracks seated state on the player, and prevents the object from being picked up:

```
@create "bar stool" from "$furniture"
@describe "bar stool" as "A cracked vinyl stool bolted to the floor."
@move "bar stool" to "The Bar"
```

Players can then `sit bar stool` and `stand`. Customize the experience with `_msg` properties:

```
@edit property sit_succeeded_msg on "bar stool" with "You perch on the cracked vinyl stool."
@edit property take_failed_msg on "bar stool" with "The stool is bolted to the floor."
```

See [object-model.md](object-model.md) for the full list of `$furniture` message properties.

## State Toggle (lock/unlock, fill/empty, on/off)

For binary state that doesn't involve sitting or opening containers, track state via a property and toggle it in a verb. (For openable containers use `$container` — it handles open/close natively.)

```python
from moo.sdk import context, NoSuchPropertyError

occupied = this.get_property("occupied")
if occupied:
    this.set_property("occupied", False)
    print("You open it.")
    context.player.location.announce_all_but(context.player, f"{context.player.name} opens it.")
else:
    this.set_property("occupied", True)
    print("You close it.")
    context.player.location.announce_all_but(context.player, f"{context.player.name} closes it.")
```

## One-Shot Event (banana peel, trap, explosive)

Fires once with full effect; subsequent triggers get an "already happened" message. Resets after one day so the event can fire again.

```python
from moo.sdk import context, NoSuchPropertyError
import datetime

try:
    last_fired = this.get_property("last_fired")
    elapsed = datetime.datetime.now() - datetime.datetime.fromisoformat(last_fired)
    cooled_down = elapsed.total_seconds() > 86400
except NoSuchPropertyError:
    cooled_down = True

if not cooled_down:
    print("Nothing more happens. The moment has passed.")
else:
    this.set_property("last_fired", datetime.datetime.now().isoformat())
    print("It happens. Dramatically.")
    context.player.location.announce_all_but(context.player, f"{context.player.name} triggers it.")
```

## Consume Item (drink, eat)

```python
from moo.sdk import context

full = this.get_property("full")
brand = this.get_property("brand")
if not full:
    print(f"The {brand} glass is empty.")
    return
this.set_property("full", False)
print(f"You drink the {brand}. Refreshing.")
context.player.location.announce_all_but(context.player, f"{context.player.name} drinks a {brand}.")
```

## Create Item on Demand (pull tap, order drink)

```python
from moo.sdk import context, create, lookup

beer_glass = lookup("Generic Beer Glass")
glass = create("a pint of Duff", parents=[beer_glass], location=context.player)
glass.set_property("full", True)
glass.set_property("brand", "Duff")
print("You pull a pint of Duff. Foam settles.")
context.player.location.announce_all_but(context.player, f"{context.player.name} pulls a pint.")
```

## NPC Dialogue (speak verb on NPC)

```python
from moo.sdk import context
import random

lines = this.get_property("lines")
msg = random.choice(lines)
print(f'{this.name} says, "{msg}"')
context.player.location.announce_all_but(context.player, f'{this.name} says, "{msg}"')
```

The `lines` property is a list of strings set via `@edit property lines on "NPC" with ["line1", "line2"]`.

## Random Outcome (dartboard, jukebox, slot machine)

```python
from moo.sdk import context
import random

outcomes = this.get_property("outcomes")
result = random.choice(outcomes)
print(f"You throw. {result}")
context.player.location.announce_all_but(context.player, f"{context.player.name} throws a dart. {result}")
```

## Prank Call Pattern (phone booth, payphone)

```python
from moo.sdk import context
import random

names = this.get_property("names")
name = random.choice(names)
print(f"You dial the number. Moe picks up.")
print(f'"Hey Moe, is {name} there?"')
print(f'Moe\'s voice: "Uh... {name}? Hey, is there a {name} in here?"')
context.player.location.announce_all_but(
    context.player,
    f"{context.player.name} is using the payphone."
)
```

## Property Access Patterns

```python
from moo.sdk import NoSuchPropertyError

# Read a property (raises NoSuchPropertyError if missing)
val = this.get_property("name")

# Read with fallback
try:
    val = this.get_property("name")
except NoSuchPropertyError:
    val = "default"

# Write a property
this.set_property("name", value)

# Access another object's property
room = context.player.location
owner = room.get_property("owner")
```

## Object Lookup

```python
from moo.sdk import lookup, NoSuchObjectError

# By name — raises NoSuchObjectError if not found (never returns None)
obj = lookup("The Bar")

# Check existence
try:
    obj = lookup("The Bar")
except NoSuchObjectError:
    print("Room not found.")
    return
```

## Invoke Another Verb

```python
from moo.sdk import invoke

# Call a verb by passing a Verb reference (obtained via attribute access)
invoke(verb=obj.verb_name, args=(arg1, arg2))

# With a delay (seconds)
invoke(verb=obj.verb_name, delay=10)
```

## Context Object

```python
context.player        # The player who ran the command
context.player.name   # Their name
context.player.location  # The room they're in
this                  # The object the verb is defined on (or matched via dspec)
args                  # List of positional args passed to the verb
kwargs                # Dict of keyword args
```

## Hidden Room via Interactive Object

An object in a visible room teleports the player to a hidden room. The hidden room has no listed exit in-world — the only entry point is this verb. Give the hidden room a normal directional exit back.

```python
from moo.sdk import context, lookup, NoSuchObjectError
print("The bookcase swings outward on hidden hinges, revealing a passage.")
try:
    context.player.moveto(lookup("The Secret Room"))
except NoSuchObjectError:
    print("The passage appears to be sealed.")
```

Use `--dspec this` on the shebang so the verb only fires when the player explicitly targets this object. Multiple trigger verb names (e.g. `pull yank`) are space-separated on the shebang line.

## Stateful Counter with Escalating Flavor Text

A numeric property counts uses; each tier produces different output. Good for consumables, actions with diminishing returns, or anything that should feel progressively different across many sessions.

Full copy-paste template: `snippets/stateful-counter.yaml`

```python
from moo.sdk import context, NoSuchPropertyError
try:
    pours = this.get_property("pours")
except NoSuchPropertyError:
    pours = 0
pours += 1
this.set_property("pours", pours)
if pours == 1:
    print("First time. Exceptional.")
elif pours == 2:
    print("Second time. Still good.")
elif pours <= 4:
    ordinal = ["third", "fourth"][pours - 3]
    print(f"This is your {ordinal} time.")
else:
    print("You reconsider.")
```

**RestrictedPython note:** `results["key"] += 1` is blocked. Use a plain local variable (`pours += 1`), then call `set_property` with the updated value.

## One-Shot State Change

A boolean property records whether an action has happened. First call: shows the full reveal and sets the flag. All subsequent calls: shows a brief summary of the already-changed state.

Good for sealed documents, puzzle items, locked boxes that stay open, one-time discoveries.

Full copy-paste template: `snippets/one-shot-state.yaml`

```python
from moo.sdk import context, NoSuchPropertyError
try:
    opened = this.get_property("opened")
except NoSuchPropertyError:
    opened = False
if opened:
    print("Already opened. Inside: ...")
else:
    this.set_property("opened", True)
    print("You open it for the first time.")
    print("The reveal happens here.")
    context.player.location.announce_all_but(context.player, f"{context.player.name} opens it.")
```
