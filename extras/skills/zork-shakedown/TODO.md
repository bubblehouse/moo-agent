# Deferred Bugs (Rule Zero / out-of-scope)

These items were found by `zork-shakedown` sessions but cannot be fixed under Rule Zero (which forbids touching `moo/` core outside the bootstrap). They sit here as a backlog. Each entry notes what would be needed to fix it. Move an item back to `BUGS.md` (and check it off there) once the deeper change has been approved and made.

Format mirrors `BUGS.md`.

---

- [ ] **Verb dispatch and article stripping are case-sensitive** (command: `LOOK`, `Take The leaflet`, `Inventory`)
  - **Response**: every command whose first token isn't all-lowercase returns "I don't know how to do that.". Object lookup IS case-insensitive (`examine MAILBOX` works), so the asymmetry is jarring. Article stripping has the same bug: `take The leaflet` → "There is no 'The leaflet' here." but `take the leaflet` works.
  - **Root layer**: moo-core parser. Two specific sites in `moo/core/parse.py`:
    1. **Verb lookup**: `_batch_get_verb` queries `Verb.objects.filter(names__name=verb_name, ...)` at lines 452 and 466. Django's default `name=...` is case-sensitive. Change to `names__name__iexact=verb_name` (Postgres LIKE-based, no functional index — verify cost) or normalise `verb_name` at the call site (line 446: `verb_name = self.words[0].lower()`). The lowercase variant is safer: it preserves the case-insensitive index and matches `parser.dobj` lookup which already lowercases.
    2. **Article stripping regex**: `Pattern.SPEC` at line 103 is `r"(?P<spec_str>my|the|a|an|...)"` — case-sensitive. Either `(?i)` prefix the alternation or `.lower()` the token before matching.
  - **What would unlock it**: explicit user approval to edit `moo/core/parse.py`. Both changes are tightly scoped (5 lines total) and have clear regression coverage via the existing parser tests.
  - **Workaround**: type everything lowercase.

- [ ] **Repetitive Parser Boilerplate**
  - This pattern appears frequently: `parser.words[0].lower() if context.parser is not None and parser.words else verb_name`; this returns whatever verb name the parser used, and falls back to the verb_name of the current verb if there's no parser context.

- [ ] **Period-separated compound commands not supported** (command: `take sword. kill troll with sword.`)
  - **Response**: `There is no 'sword. kill troll with sword' here.`
  - **Root layer**: moo-core parser. The whole input string is treated as a single command. Canonical Zork I splits on `.`, `,`, and `THEN` at the input layer.
  - **What would unlock it**: a pre-tokenization splitter in the parser entry point that splits the raw input on those separators and queues each fragment as a separate command. The bootstrap can't reach this from `do_command` — by the time do_command runs the lexer has already tokenized; re-lexing would need access to `Lexer`/`interpret`, neither of which is in `moo.sdk`. Care needed for quoted strings (`say "hello sailor."` should NOT split).

- [ ] **Print/tell ordering pipeline — output one command behind** (commands: any with print() output)
  - **Response**: every command's output appears in the next command's window.
  - **Root layer**: Celery task buffering of `print()` vs synchronous PREFIX/SUFFIX emission in the shell handler. Either the shell handler must synchronously await the Celery task's print buffer before emitting SUFFIX, or RestrictedPython's print() needs to write through to `player.tell()` for player-dispatched verbs.
  - **What would unlock it**: investigate the shell handler's PREFIX/SUFFIX flow — find where the harness's "since marker" matching runs, and whether the Celery task can be awaited before SUFFIX. If yes, sync wait. If not, switch the translator's emitter to `player.tell(...)` for verbs that run on the player's behalf (NOT `caller.tell()` per direct user feedback).

- [ ] **IAC GA bytes leak into harness output as `��`** (every prompt; visible only when verbs return no synchronous output — diagnostic noise, not a gameplay blocker)
  - **Response**: bare `��` in place of empty-output verbs. The bytes are `0xFF 0xF9` (IAC GA) decoded with `errors="replace"` by pexpect.
  - **Hypothesis**: [moo/shell/server.py:147](moo/shell/server.py#L147) couples raw mode and IAC: `iac_enabled = _is_mud_term(term)` and `_is_mud_term` whitelists `xterm-256-basic` (the same TERM that triggers raw mode at line 145–146). The harness uses `TERM=xterm-256-basic` because it needs raw mode to avoid prompt_toolkit CPR delay (see [extras/skills/game-designer/tools/moo_ssh.py:107-114](extras/skills/game-designer/tools/moo_ssh.py#L107-L114)) but is **not** a MUD client and can't consume IAC. After every prompt render [moo/shell/prompt.py:634-653](moo/shell/prompt.py#L634-L653) writes `IAC GA` (0xFF 0xF9). Inside normal verb output the GA is invisible after "Taken." etc.; when a verb (like the broken sword take) returns no synchronous content, all the harness sees IS the GA.
  - **Fix path**: decouple raw mode from IAC. Either (a) a second raw-mode TERM (`xterm-256-basic-noiac` or similar) that flips raw without joining the MUD-client allowlist; (b) gate IAC on a separate signal (negotiation reply rather than TERM); or (c) make the harness explicitly opt out via an env var or a session setting.
  - **Workaround**: harness sees garbage, not output, for any silent-return verb — diagnoses look like verb crashes when they're really empty returns plus IAC GA.

- [ ] **Multi-print artifacts split sentences awkwardly across newlines** (rooms: many, in mailbox-open / score / room descriptions)
  - **Response**: `Opening the small mailbox reveals \na leaflet\n.`; `Your score is 0 (total of 350 points), in 4\n moves.`; `In one corner of the house there is a small window\nwhich is \nslightly ajar.` Period or trailing fragment lands on its own line because each piece arrives as a separate `print()`.
  - **Hypothesis**: the translator generates `print(prefix); print(name); print(".")` for the canonical TELL/PRINTC sequences. Each `print()` adds a newline. Two viable fixes: (a) collapse adjacent string-literal prints in the translator into a single f-string, or (b) emit `print(..., end="")` for non-final pieces.
  - **Workaround**: cosmetic — gameplay isn't blocked, but score / object-listing / room-description text reads as ungrammatical chunks.

- [ ] **B5. Drop the System Object atom registry**
  - Translated runtime calls already use `lookup("atom")`. The System Object property registry (`_.set_property("rope", obj)`) is kept only for `--on $atom` shebang resolution at verb-load time. Replacing that lookup with an alias lookup in `moo/bootstrap/__init__.py` would let us drop the registry entirely. **Boundary of Rule Zero** (touches the shared loader, not parse.py / sdk) — design conversation needed before touching it.

- [ ] **Dead-object error message** (room: `Kitchen`, command: `eat lunch` after eating it)
  - **Response**: `I don't know how to do that.`
  - **Root layer**: moo-core parser error classification. When the parser can't find a verb that matches because the dobj has been consumed, it falls through to the no-verb error instead of producing a no-object error. Canonical Zork would say "There is no lunch here." instead.
  - **What would unlock it**: distinguish at the parser level between "verb_name is unknown" and "dobj_str doesn't resolve to a real object in scope". The latter case (parser found a verb-name match but no object) should raise a different exception that the dispatch loop can convert to "There is no X here." The former should keep the current "I don't know how to do that." message.
  - **Workaround**: cosmetic only; the action is correctly refused.
