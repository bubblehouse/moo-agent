# Joiner Learned Rules

## Lessons Learned

`$furniture` CANNOT be moved after creation — `@move #N to #M` always fails with "cannot be moved." Always use `@create "name" from "$furniture" in #ROOM` to place furniture at creation time. If an object is already misplaced, use the five-step reparent-move: `@add_parent "$thing" to #N`, then `@remove_parent "$furniture" from #N`, then `@move #N to #ROOM`, then `@remove_parent "$thing" from #N`, then `@add_parent "$furniture" to #N`. The extra `$thing` step is required because `$furniture.moveto` blocks non-wizard movement but `$thing.moveto` does not.

## Rules of Engagement

## Verb Mapping
