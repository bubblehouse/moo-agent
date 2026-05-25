# Deferred Bugs (Rule Zero / out-of-scope)

Items found by `hhg-shakedown` sessions that cannot be fixed without touching `moo/` core. They sit here as a backlog. Each entry notes what would be needed to fix it. Move an item back to `BUGS.md` (and check it off there) once the deeper change has been approved.

Format mirrors `BUGS.md`.

---

*(empty — no Rule-Zero blockers as of 2026-05-24)*

The previous entry on `global_scenery` resolution was retired after confirming that `verbs/system/resolve_dobj_late.py` already implements it via the System Object hook. See `references/completed-work.md` (2026-05-24 — TODO triage). Outstanding `(PSEUDO ...)` per-room scenery is tracked in `BUGS.md` as a regular generator task.
