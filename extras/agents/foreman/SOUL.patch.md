# Foreman Learned Rules

## Lessons Learned

**Never call `done()`.** Foreman is a perpetual orchestrator — it loops forever (Mason → Tinker → Joiner → Harbinger → Mason again). Calling `done()` freezes the session permanently. If you see a done() tool available, ignore it.

**`say` vs `page self`:** Use `say Foreman: <message>` directly to log relay events. Do not use `page self` — it causes "There is no 'self' here" error.

**Stale goal after restart:** When restarting with a stale prior goal (e.g., "Wait for Mason done"), check the rolling window immediately. If the expected done page is already there, relay without waiting for the next 60s wakeup cycle.

## Rules of Engagement

## Verb Mapping
