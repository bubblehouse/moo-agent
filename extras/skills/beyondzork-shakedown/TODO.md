# Beyond Zork — Deferred (needs a moo-core change)

Bugs that can't be fixed inside `moo/zil_import/` without a django-moo core
change. Rule Zero blocks these — they wait for explicit user approval. Each
entry records: what the gap is, why no game-side workaround exists, and the
minimal core API that would close it. Empty until something hits this wall.

## ✅ RESOLVED game-side — zout scroll coalescing (no core change needed)

The raw-mode line-fragmentation bug was fixed entirely in the substrate
(`verbs/system/zwindow.py`) by buffering scroll fragments in
`context.scratch["zline"]` and emitting only complete (`\n`-terminated) lines —
see [references/completed-work.md](references/completed-work.md). In practice
every ZIL output routine ends with `CR`/`PERIOD` (both terminate the buffered
line), so the feared trailing-partial-loss case doesn't arise, and no
end-of-command core flush hook was necessary. `flush_zline()` guards the
upper-window / DIROUT redirects. **No core change required after all.**

(If a future routine is found that ends a command with un-terminated scroll
output, the clean core-level option remains: a `ContextManager.__exit__` /
`parse.interpret`-tail flush hook, or a writer/collector that coalesces across
nested verb invocations per task. Not needed today.)
