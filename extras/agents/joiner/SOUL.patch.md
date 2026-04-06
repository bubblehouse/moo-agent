# Joiner Learned Rules

## Lessons Learned

`$furniture` CANNOT be moved after creation — `@move #N to #M` always fails for furniture with "cannot be moved." The ONLY way to place furniture in a room is to create it there directly: `@create "name" from "$furniture" in #ROOM`. Never create furniture first and move it second. The `in #ROOM` argument is mandatory, not optional.

## Rules of Engagement

## Verb Mapping
