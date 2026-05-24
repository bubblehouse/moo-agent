# Deferred Bugs (Rule Zero / out-of-scope)

These items were found by `zork-shakedown` sessions but cannot be fixed under Rule Zero (which forbids touching `moo/` core outside the bootstrap). They sit here as a backlog. Each entry notes what would be needed to fix it. Move an item back to `BUGS.md` (and check it off there) once the deeper change has been approved and made.

Format mirrors `BUGS.md`.

---

- [ ] **Case-insensitive article stripping (residual after 2026-05-17 dispatch fix)** (command: `Take The leaflet`)
  - **Response**: `There is no 'The leaflet' here.` Verb dispatch is now case-insensitive (`LOOK`, `Inventory` work) but the article-stripping regex in `Pattern.SPEC` ([moo/core/parse.py:103](moo/core/parse.py#L103)) still requires lowercase `my|the|a|an`.
  - **Why it wasn't fixed in the dispatch PR**: a naive `(?i:my|the|a|an)` made the regex strip `The` from prepositional phrases like `@dig north to The Laboratory` — the verb's `get_pobj_str("to")` then returned `"Laboratory"` and `lookup("Laboratory")` failed (the room is named "The Laboratory"). The lexer extracts `spec_str="The"` + `obj_str="Laboratory"` but `find_object`'s retry-with-spec only updates the dobj record, not pobj records; `get_pobj_str` returns the bare `obj_str`.
  - **What would unlock it**: extend the existing dobj retry-with-spec logic to prepositional records — update `record[0]`/`record[1]` on successful retry so verbs reading `get_pobj_str` see the combined name. Then the `(?i:...)` switch becomes safe.
  - **Workaround**: type articles lowercase (the existing reliable behaviour).

- [ ] **Print/tell ordering pipeline — output one command behind** (commands: any with print() output)
  - **Response**: every command's output appears in the next command's window.
  - **Root layer**: Celery task buffering of `print()` vs synchronous PREFIX/SUFFIX emission in the shell handler. Either the shell handler must synchronously await the Celery task's print buffer before emitting SUFFIX, or RestrictedPython's print() needs to write through to `player.tell()` for player-dispatched verbs.
  - **What would unlock it**: investigate the shell handler's PREFIX/SUFFIX flow — find where the harness's "since marker" matching runs, and whether the Celery task can be awaited before SUFFIX. If yes, sync wait. If not, switch the translator's emitter to `player.tell(...)` for verbs that run on the player's behalf (NOT `caller.tell()` per direct user feedback).

- [ ] **IAC GA bytes leak into harness output as `��`** (every prompt; visible only when verbs return no synchronous output — diagnostic noise, not a gameplay blocker)
  - **Response**: bare `��` in place of empty-output verbs. The bytes are `0xFF 0xF9` (IAC GA) decoded with `errors="replace"` by pexpect.
  - **Hypothesis**: django-moo's `moo/shell/server.py:147` couples raw mode and IAC: `iac_enabled = _is_mud_term(term)` and `_is_mud_term` whitelists `xterm-256-basic` (the same TERM that triggers raw mode at line 145–146). The harness uses `TERM=xterm-256-basic` because it needs raw mode to avoid prompt_toolkit CPR delay (see `extras/skills/game-designer/tools/moo_ssh.py:107-114`) but is **not** a MUD client and can't consume IAC. After every prompt render `moo/shell/prompt.py:634-653` writes `IAC GA` (0xFF 0xF9). Inside normal verb output the GA is invisible after "Taken." etc.; when a verb (like the broken sword take) returns no synchronous content, all the harness sees IS the GA.
  - **Fix path**: decouple raw mode from IAC. Either (a) a second raw-mode TERM (`xterm-256-basic-noiac` or similar) that flips raw without joining the MUD-client allowlist; (b) gate IAC on a separate signal (negotiation reply rather than TERM); or (c) make the harness explicitly opt out via an env var or a session setting.
  - **Workaround**: harness sees garbage, not output, for any silent-return verb — diagnoses look like verb crashes when they're really empty returns plus IAC GA.

- [ ] **B5. Drop the System Object atom registry**
  - Translated runtime calls already use `lookup("atom")`. The System Object property registry (`_.set_property("rope", obj)`) is kept only for `--on $atom` shebang resolution at verb-load time. Replacing that lookup with an alias lookup in `moo/bootstrap/__init__.py` would let us drop the registry entirely. **Boundary of Rule Zero** (touches the shared loader, not parse.py / sdk) — design conversation needed before touching it.

- [ ] **`examine boat` disambiguation prompt has stray comma** (room: Dam Base with both magic and punctured boat, command: `examine boat`)
  - **Response**: `When you say, "boat", do you mean , #206 (magic boat) or #216 (punctured boat)?` — doubled comma between "do you mean" and "#206".
  - **Root layer**: parser ambiguity prompt format string in `moo/core/parse.py`. The leading `,` belongs to a multi-candidate join (`, #A or #B`) that doesn't strip when the list starts.
  - **What would unlock it**: find the f-string / join in `moo/core/parse.py` that builds the ambiguity prompt and either skip the leading separator or use a proper comma-join helper.
  - **Workaround**: use the adjective to disambiguate (`examine magic boat`).

- [ ] **Compound-command splitter is conservative — cardinal-direction shorthand `n,n,e` no longer splits** (regression from 2026-05-17 fix)
  - **Response**: the splitter landed in `interpret()` requires `,` or `.` to be followed by whitespace + alpha to split. `n,n,e` (no spaces) is not split — it dispatches as a single unknown command.
  - **Why it wasn't fixed**: protecting `[1, 2, 3]` JSON in `@set obj prop [1, 2, 3]` required a "no split inside brackets" rule plus "no split unless followed by whitespace + alpha". Cardinal shorthand `n,n,e` falls outside that envelope.
  - **What would unlock it**: a movement-only pre-pass that splits cardinal shorthand on `,` regardless of whitespace, run BEFORE the general splitter. Or normalise the input to add a space after commas in `<dir>,<dir>` sequences when none of the tokens contain digits or brackets.
  - **Workaround**: type `n, n, e` (with spaces) — the splitter handles that.
