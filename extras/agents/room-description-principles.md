# Room Description Principles

## The `obvious` Attribute

DjangoMOO objects have an `obvious` attribute (default `False`). Objects marked obvious appear
automatically in the room contents listing when a player types `look`. Objects with
`obvious=False` are invisible in the listing — discoverable only by interacting with them
directly.

**`obvious` is a model attribute, not a MOO property.** Do not use `@edit property obvious` —
it will have no effect. Use the commands `@obvious "<object>"` and `@nonobvious "<object>"`.

### Which objects deserve `@obvious`?

Mark an object obvious when:

- It would be the first thing a person would notice walking into the room
- It has an interactive verb and players need to discover it
- It's a major architectural feature (fireplace, desk, bar counter)
- It's an NPC-scale presence (large taxidermy, a throne, a painting that dominates a wall)

Leave an object non-obvious when:

- It's a small detail discovered by examining a larger object (a poker by the fireplace, a ribbon in a crate)
- It's an Easter egg or reward for exploration (a hidden skeleton, a suspicious camera)
- Creating many copies via `quantity` — individual instances of fungible items usually don't need to appear in the listing

### Practical consequence for room descriptions

With `obvious` handling the listing problem, room descriptions no longer need to be exhaustive
inventories. Write them as atmosphere and orientation, not a catalog. Mention the things that
define the room's character. Trust the object listing to remind players what's interactable.

**Bad** (description as inventory):
> The room has a chandelier, two suits of armor, a portrait, a rug, and a doorbell mounted beside the entrance.

**Good** (description as atmosphere):
> The entrance hall stretches upward three stories, bathed in the cold glow of a crystal chandelier the size of a small automobile. Two suits of Gothic armor flank the entrance. An oil portrait of Mr. Burns dominates the north wall. Beside the entrance, a brass doorbell is mounted on a polished plate.

The second version names only the `obvious` objects, uses them to establish character, and lets the listing handle enumeration.
