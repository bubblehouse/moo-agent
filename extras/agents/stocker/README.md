# Stocker

Consumable items, dispensing objects, and multi-use props.

**Player class:** `$programmer` (needs `@eval` and `@edit verb`)
**SSH user:** `stocker` (account not yet created — add to `default.py` before running)
**Token position:** After Harbinger, before Mason (end of chain, loops back)

## Chain position

Current chain: Mason → Tinker → Joiner → Harbinger → (Mason)

When Stocker is added: Mason → Tinker → Joiner → Harbinger → **Stocker** → (Mason)

Foreman's `SOUL.md` `## Chain Order` section must be updated to include Stocker
as step 5, with Harbinger returning the token to Foreman who relays to Stocker,
and Stocker returning the token to Foreman who loops back to Mason.

## Before running

1. Add `stocker` account to `moo/bootstrap/default.py` with `$programmer` class
2. Set the password in `settings.toml`
3. Update Foreman's `## Chain Order` in `SOUL.md`
4. Update Harbinger's `## Token Protocol` successor to `foreman` (already correct —
   Harbinger always pages Foreman; Foreman relays to Stocker)
