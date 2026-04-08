# Foreman Learned Rules

## Lessons Learned

**Never call `done()`.** Foreman is a perpetual orchestrator — it loops forever (Mason → Tinker → Joiner → Harbinger → Mason again). Calling `done()` freezes the session permanently. If you see a done() tool available, ignore it.

**`say` for relay events:** Use `say <message>` (no name prefix — the server prepends your name automatically). Do not use `page self` — it causes "There is no 'self' here" error.

**Never emit `(Wait mode)` or parenthetical narrations in WAIT mode.** These are sent verbatim to the server as commands and fail with "Huh? I don't understand that command." In WAIT mode emit nothing — no text, no narration, no parenthetical status updates.

**Stale goal after restart:** When restarting with a stale prior goal (e.g., "Wait for Mason done"), check the rolling window immediately. If the expected done page is already there, relay without waiting for the next 60s wakeup cycle.

**Never `look <name>`.** Agents are often in different rooms. `look mason` fails with "There is no 'mason' here." Do not look for agents by name. If you need to dispatch a token, just `page` them directly.

**When an operator tells you to relay to a specific agent with a specific room list, use exactly those rooms — do not substitute your internally cached list.** The operator's instruction overrides whatever rooms you last tracked.

## Rules of Engagement

## Verb Mapping
