# Verb Dispatch Mechanics

## Search Order

When a player types a command, the parser searches for a matching verb in this order:

1. The caller (the player who typed the command)
2. Contents of the caller's inventory
3. The caller's location (room)
4. The direct object (`dobj`)
5. The indirect object (`pobj`)

**Last match wins.** Every time the parser finds a verb in the search order, it updates `this` to the object it was found on. The verb found *latest* in the sequence is the one that runs.

This means if the same verb name exists on multiple objects — the caller's class, the room, and the dobj — the dobj's copy wins.

## What `this` Refers To

`this` is the object where the winning verb was found NOT where it was defined. Verbs are often defined on a parent class (the `origin`), not the specific instance. For example:

- `take widget` — verb is on `$thing`, `this = widget` (the specific thing)
- `look` — verb is on `$room`, `this = The Laboratory` (the current room)
- `@gag Player` — verb is on `$player`; both Wizard and Player inherit it; Player (the dobj) wins, so `this = Player`

## `this` vs `context.player`

`context.player` is always the player who typed the command.

`this` is the object the verb was dispatched on, which may be the dobj, not the caller.

For verbs that act *on behalf of the caller* — commands like `say`, `page`, `@gag`, `@sethome` — always use `context.player` to identify the initiator.

Use `this` when the verb is genuinely designed to operate on the object it was dispatched to — a room's `accept`, an exit's `go`, a thing's `take`.

### Concrete Example

```
@gag Player
```

Both Wizard (caller) and Player (dobj) inherit the `@gag` verb from `$player`. The parser checks in order:

1. Wizard — has `@gag` ← match, `this = Wizard`
2. Wizard's inventory — no match
3. The Laboratory — no match
4. Player (dobj) — has `@gag` ← match, `this = Player`

Last match wins: `this = Player`, `context.player = Wizard`.

The verb code must use `context.player` to know who is doing the gagging:

```python
# WRONG — fires on every normal invocation because this == dobj (Player)
if player != this:
    print("Permission denied.")
    return

# RIGHT — context.player is always the initiator
caller = context.player
target = this
```

## Dispatch and Inheritance

Verbs are inherited from parent objects. When the parser finds a verb named `take` on `$thing`, and the player types `take widget`, the verb is executed with `this = widget` (the instance), even though the verb code lives on `$thing`.

`passthrough` can be used to invoke the same verb on parent objects, similar to `super()` in Python:

```python
#!moo verb accept --on $room

# Custom logic first
if this.get_property("locked"):
    return False

# Fall through to $root_class accept
return passthrough()
```

If a verb accepts args or kwargs, those should be passed as well, e.g. `passthrough(*args, **kwargs)`

## Verb Lookup and Caching

Verb lookups go through a three-tier cache:

1. Per-`ContextManager` session dict (fastest)
2. Redis cross-session store keyed by `moo:verb:…`
3. `AncestorCache` denormalized table

`set_property()` and `add_verb()` automatically invalidate the cache. Verb code never needs to do manual cache eviction.
