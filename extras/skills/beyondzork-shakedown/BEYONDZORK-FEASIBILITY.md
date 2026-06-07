# Beyond Zork — Feasibility Assessment

Status as of 2026-06-06: **scaffold-only (no regen attempted), but the display
layer is now assessed as feasible.** This doc separates two independent
questions that earlier drafts ran together:

1. **Display** — can DjangoMOO's terminal frontend render Beyond Zork's
   colored text, character graphics, and split-screen map? **Yes, with one new
   core capability (a general windowed-output mode).**
2. **Importer** — can `moo/zil_import/` translate the v5 game and its RPG
   layer? **Not yet; this is still the gate on actually running it.**

## Z-machine version (corrected)

Beyond Zork is **`<VERSION XZIP>` — Z-machine v5**, verified in
`beyondzork/beyond.zil`. It is **character-cell only**: colored/styled text
plus a fixed top window holding a stats line and an ASCII auto-map. There are
no bitmaps.

Bitmaps belong to the later **YZIP (v6)** generation (framed pictures,
graphical mini-games), which is a different engine entirely. Earlier notes
tagged Beyond Zork as YZIP/graphics; that was wrong and has been corrected in
`moo/zil_import/game_config.py` (the `BEYONDZORK_CONFIG` blurb and the
stub-config comment).

## What Beyond Zork actually does on screen

Opcode census across the v5 source (`grep` over `*.zil`):

| ZIL opcode | calls | Z-machine op | DjangoMOO mapping | Status |
| --- | --- | --- | --- | --- |
| `HLIGHT` | 171 | `set_text_style` | Rich `[bold]`/`[reverse]`/`[underline]` | already supported |
| `COLOR` | 61 | `set_colour` | Rich `[red on black]` | already supported |
| `FONT` | 41 | `set_font` (font 3) | Unicode box-drawing glyphs (plain text) | trivial |
| `CLEAR` | 15 | `erase_window` | clear upper-window buffer | needs window model |
| `CURSET` | 10 | `set_cursor` | grid-address the upper window | needs window model |
| `SCREEN` | 9 | `set_window` | route output to upper vs lower | needs window model |
| `SPLIT` | 8 | `split_window N` | set upper-window height | needs window model |
| `DIROUT`/`BUFOUT` | 37 | output streams / buffer mode | measure/buffer, mostly ignorable | minor |

`misc.zil` confirms the layout is the split screen we care about:

- `S-WINDOW` is the upper window; `S-TEXT` is the lower scrolling window.
  `TO-TOP-WINDOW` / `TO-BOTTOM-WINDOW` flip between them via `<SCREEN ...>`.
- The upper window resizes dynamically: `<SPLIT 2>` for a status line,
  `<SPLIT 12>` to show the full auto-map.
- The live map (`NEW-MAP` / `CLOSE-MAP` / `FAR-MAP`, `ROOMS-MAPPED`, `MAPY`)
  is drawn by cursor-addressing the upper window (`<CURSET 12 2>` etc.) in
  font 3, the character-graphics font. Font-3 glyphs map cleanly to Unicode
  box-drawing characters.

So Beyond Zork's "graphics" are colored/styled text plus a fixed top pane with
a stats line and an ASCII map. No bitmaps anywhere.

## Display feasibility, by pillar

1. **Color + text styling — already done.** `moo/shell/prompt.py`
   (`writer`, ~L1104-1140) renders Rich markup through `Console.capture()` →
   `print_formatted_text(ANSI(...))`, with `quiet_mode` stripping color for
   accessibility. `HLIGHT` / `COLOR` translate directly to Rich tags at the
   generator/SDK layer. No core change.

2. **Character graphics (map glyphs) — trivial.** Font 3 is a fixed glyph
   table; the translator emits the box/line characters as Unicode text, which
   flows through the same Rich pipeline. No rendering work.

3. **Split screen — the real engineering, and achievable.** The codebase
   already proves prompt-toolkit can do a fixed region over the SSH channel:
   `moo/shell/editor.py` (~L90-99) runs a full-screen `Application` with
   `HSplit([Frame(editor), status_bar])`. The gap is that the *main game loop*
   is a `PromptSession` + a `process_messages` coroutine that prints scrolling
   output above the prompt via `run_in_terminal` (`prompt.py` ~L1186-1217) —
   a different prompt-toolkit mode from a full-screen layout. A persistent top
   pane means running the session inside a full-screen `Application`, roughly
   `HSplit([top_window(dynamic height), scrolling_text_window, input])` (the
   standard full-screen-chat pattern). The editor/paginator already enter and
   exit that mode temporarily; this makes it an optional persistent mode for
   the whole session.

## Making it "sufficiently general"

The window region should be a general core capability, driven by an SDK
surface that mirrors `open_editor` / `open_paginator` / `open_input` in
`moo/sdk/output.py` — e.g. a `status_region` / `set_window` / `window_write`
API plus Kombu events the SSH server routes. Any game or builder verb could
then paint a top pane (a combat HUD, a shop list, a minimap), not just Beyond
Zork. The ZIL side (translating `SPLIT` / `SCREEN` / `CURSET` / `FONT` into
calls against that SDK) lives entirely in `moo/zil_import/` and
`verbs/beyondzork/`.

**Rule Zero note:** touching `moo/shell` is core territory, but a general
windowed-output mode is *not* a ZIL-specific change, so it is legitimate core
work — provided it is built as a game-neutral feature and authorized
explicitly, never smuggled in as a beyondzork hack. See
[../_shared/references/rule-zero.md](../_shared/references/rule-zero.md).

## What's still gated on the importer

The display work above is independent of actually running the game. Unchanged
gates on translation:

- **XZIP/v5 translation** has never been attempted (importer targets the EZIP
  family). Parser-form coverage, `<VERSION>` handling, object-table
  differences all need work.
- **RPG layer** — STRENGTH / DEXTERITY / ENDURANCE / INTELLIGENCE / COMPASS,
  combat resolution, levelling, spellcasting, character generation — a genre
  shift (CRPG) the static-world translator has never modeled. This almost
  certainly belongs in `moo/zil_import/verbs/beyondzork/` as game-specific
  runtime behaviour, not in the shared translator.
- **Heavy custom parser** — a reworked `parser.zil` with its own grammar plus
  monster/people-driven dynamic scope.

## Recommendation

The display question, which was the scary unknown, resolves favorably: Beyond
Zork needs character-cell rendering only, and a general split-screen window
mode covers it (and adds capability the core game wants anyway). That window
mode can be prototyped against a hand-written status-bar verb today — no ZIL
involved — to prove the architecture before any XZIP work begins.

The importer remains the long pole: a v5 + CRPG port is still the biggest of
the candidate titles to translate. Sequence it after the display capability
exists and after the EZIP sequels (Zork 2/3) are solid. When importer work
begins, start with a throwaway regen to capture the first failures here.

## Throwaway XZIP regen — 2026-06-06

First regen attempted: `uv run python -m moo.zil_import
~/Workspace/beyondzork/beyond.zil --game-config beyondzork --output
moo/bootstrap/beyondzork`.

**The XZIP source parses cleanly.** All 12 `<INSERT-FILE>` members
(CONSTANTS, MACROS, SYNTAX, MISC, PARSER, VERBS, EVENTS, PEOPLE, MONSTERS,
PLACES, THINGS, RARITIES) tokenize and parse. World-model extraction reports:

| | count |
| --- | --- |
| Rooms | **0** |
| Objects | 448 |
| Routines | 1717 |
| Globals | 554 |
| Syntax | 233 |
| Synonyms | 10 |

Generation then crashes in `generator/_gen_objects`:
`TypeError: unhashable type: 'list'` at `if obj.location and obj.location in
rooms` — a Beyond Zork object's `location` is a *list*, not a single atom.

So the gates on a *running* Beyond Zork are world-model extraction, not the
parser or routine translation:

1. **Rooms: 0.** The room detector finds no rooms — Beyond Zork marks rooms
   differently from the EZIP family (`PLACES.zil` has 392 forms). Room
   extraction needs an XZIP-aware path.
2. **`location` as a list.** Object `LOC`/placement parses to a list; the
   generator assumes a hashable atom. Object extraction + `_gen_objects` need
   to handle the v5 shape.
3. Plus the RPG layer and custom parser noted above.

Crucially, **routine translation works** — all 1717 routines extract, and the
display routines (`misc.zil`'s `TO-TOP-WINDOW` / `NEW-MAP` / the status line)
translate. That is what the display driver targets.

## Display-driver status (window SDK ↔ ZIL)

The django-moo windowed-display capability ships on branch
`feat/windowed-game-support` (SDK `open_window` / `window_write` /
`window_cursor` / `window_emit` / `window_clear` / `window_split` /
`close_window` / `window_supported`, the full-screen shell layout, and a GMCP
`Window.*` package).

The game-neutral translation layer maps Beyond Zork's display opcodes onto that
SDK (branch `feat/beyondzork-window-driver`, in `moo/zil_import/translator/`):

| ZIL opcode | emits |
| --- | --- |
| `SPLIT n` | `window_split(context.player, n)` |
| `SCREEN ,S-WINDOW` / `1` | select upper window (routes later `TELL`) |
| `SCREEN ,S-TEXT` / `0` | select lower window (`TELL` → `print`) |
| `CURSET r c` | `window_cursor(context.player, r, c)` |
| `TELL ...` while upper | `window_emit(context.player, ...)` |
| `CLEAR` / `DCLEAR` | `window_clear(context.player)` |
| `HLIGHT` / `COLOR` / `FONT` / `BUFOUT` / `DIROUT` / `CURGET` | safe no-op comment (not yet modelled) |

Covered by unit tests in `tests/test_translator.py`. **Known limit:** `SCREEN`
routing is tracked statically *within a routine*. Beyond Zork switches windows
via helper calls (`TO-TOP-WINDOW` does the `<SCREEN>`), so a `TELL` in a
routine that called the helper is not yet recognised as upper-window output —
this needs a runtime current-window model (a future `window_screen` SDK call
or a cross-routine analysis pass).

**Live verification is blocked** on the world-model extraction above: until
Beyond Zork can stand up a `beyondzork.local` site (rooms + object locations),
the translated display routines can't be exercised end-to-end. Next steps when
that work begins: (1) XZIP room detection, (2) list-shaped `location` handling,
(3) a runtime window-target so cross-routine `SCREEN` switches route `TELL`
correctly, then drive the status line + `NEW-MAP` over SSH against the Phase A
window UI.

## World model now stands up — 2026-06-06 (live)

`beyondzork.local` is live (**Site PK 7**, 127 rooms / 321 objects, zero
tracebacks at bootstrap). The world-model gate is cleared and basic navigation
works. All importer changes are game-agnostic (keyed on a Z-machine **dialect**,
never on Beyond Zork names) and EZIP output is byte-identical (the
bootstrap-consistency suite for Zork 1/2/3 + HHG still passes). 246 importer
tests pass.

**What landed (all in `moo/zil_import/`):**

1. **XZIP dialect knobs** on `GameConfig` — `rooms_as_objects`,
   `placement_property` (`"LOC"`), `in_is_direction`. EZIP defaults unchanged.
2. **Room-as-object extraction** — `<OBJECT … (LOC ROOMS) (FLAGS … LOCATION)>`
   forms reclassify into rooms (127 found, was 0). Both markers required so a
   `(LOC GURDY)` object stays an object.
3. **`(LOC …)` placement** + `(IN …)` treated as the enter-direction exit (this
   was the source of the unhashable-`list` crash — `(IN <TO …>)` was misread as
   a container). A defensive guard in `_gen_objects` degrades any stray non-atom
   location to "unplaced" instead of crashing.
4. **Nested exit forms** — `_parse_exit` unwraps XZIP's `<…>` exit values and
   handles `<TO room>`, `<PER routine>`, `<SAY-TO room "msg">`, `<SORRY "msg">`
   (blocked), `<THRU door room>`. 116 direct-dest + 88 procedural exits now
   resolve (was 0 navigable). `<TABLE …>` flying/vehicle exits and bare `(DIR 0)`
   placeholders remain `None` (noisy "Could not parse exit" warnings, harmless).
5. **General ZIL library-macro predicates** — handlers for `HERE?`
   (`context.player.here()` membership), `IS?` (delegates to `FSET?`), and `T?`
   (delegates to `NOT ZERO?`). These were emitting undefined `here_p` / `is_p` /
   `t_p` calls (NameErrors) in every describe/logic routine. ~1850 call sites
   fixed. EZIP games don't use these macros, so their output is unchanged.
6. **Dedicated reset body** `_beyondzork_reset_state_body.py` (parks the
   Adventurer at the Hilltop opening room; `reset_body_filename` set on
   `BEYONDZORK_CONFIG`). Required — without it beyondzork inherits zork1's body
   and corrupts the site mid-init.

**Verified live** (parser-dispatched, as the Adventurer):
`look` → prints the room title ("Hilltop"); `east` → moves to Cove; `west` →
back to Hilltop. Movement and exit resolution work.

**Display driver confirmed wired, not yet visually exercised.** Generated verbs
import the window SDK and route through it — 22 `window_split`, 26
`window_emit`, 32 `window_clear`, 16 `window_cursor` calls across helpers like
`setup_top`, `show_setline`, `do_curset`, `ibm_box`. `<HLIGHT>`/`<COLOR>`/`<FONT>`
remain safe no-op comments (the known limit above).

**Next frontier (the deferred RPG/display layer):** full room *descriptions*
hit the auto-map / exit-table machinery — `MSB`/`LSB` byte-decode of exit-type
tables (`XTYPE`), `<TABLE …>` exits, and `SETUP-CHARACTER` / `SNAMES` / `SETOFFS`
zstate the minimal reset doesn't seed. The next undefined name on `look` is
`msb`. This is the font-3 auto-map + RPG-character work, exactly the long pole
the recommendation above flagged. Visual windowed-display verification still
needs an interactive rich-mode SSH session (raw-mode harnesses no-op the window
Application); the planned GMCP `Window.*` capture harness is the path there.

## Describe-path drive — 2026-06-06 (session 2)

Pushed the `look` path further. **Four more general ZIL library-macro handlers
landed** in `translator/expr_handlers.py` (all game-agnostic, EZIP byte-identical,
248 importer tests pass):

- `MSB` → `(word & 0xff00)`, `LSB` → `(word & 127)` (delegate to `BAND`; the
  `XTYPE` high/low-byte decode).
- `DLESS?` → `(var := var - 1) < val`, `IGRTR?` → `(var := var + 1) > val`
  (Z-machine `dec_chk`/`inc_chk`; walrus so the loop-step side-effect lands in
  expression position — RestrictedPython compiles `:=`).

**The macro chain is now exhausted for the `look` path.** The remaining blocker
is **not a macro — it is the auto-map's dependence on the Z-machine exit-table
representation**, which DjangoMOO does not model:

- `mark_exits` loops `DIR` from `,P?NORTH` down to `,P?DOWN`. The `P?<dir>`
  constants are *compiler-assigned property numbers* (defined nowhere in source,
  used in `PDIR-LIST`/`XPDIR-LIST` in `constants.zil`) and are **not seeded** →
  `dir` is `None`, the walrus arithmetic raises `TypeError`.
- `<GETP ,HERE .DIR>` fetches a direction's exit by *property number*; DjangoMOO
  stores exits as an `exits` list of exit objects, so there is no numbered slot.
  (The generator currently emits `player.here().getp(".dir")` — a literal, which
  finds nothing.)
- Each room would need an `XTYPE` exit-type table keyed by those numbers for
  `mark_exits` / `display_place` (the live map) to mark/draw anything.

And `V-LOOK` is **monolithic**: `say_here` (title ✓) → `mark_exits` (auto-map) →
`describe_here` (body) → `upper_sline`/`lower_sline` (status-line window
painters, need character stats) → `display_place` (map render). There is no
clean "text-only" path; the routine always drives the status line + map, which
need `SETUP-CHARACTER` stats and `DMODE`/`SHOWING-*` display zstate.

**So the describe path is gated on a representation-mapping sub-project**, not
more macros: (1) a `P?<dir>`→property-number model + per-room `XTYPE` exit
tables (the bridge between the Z-machine exit representation and DjangoMOO's
exit objects), and (2) running `GO`'s init routines (`INITVARS` / `STARTUP` /
`SETUP-CHARACTER`) during reset to seed the RPG + display zstate. Fix (2) alone
lets `V-LOOK` run end-to-end (firing the window painters — the display-driver
verification we want) even before the map is faithful; fix (1) makes the map
real. This is the long pole; sequence the GMCP capture harness after `V-LOOK`
paints something.

> **Correction (next entry):** "(1)" above over-stated the problem. DjangoMOO
> core has **no exit concept at all** — exit objects in an `exits` list are just
> the *default/zork bootstrap* convention. The beyondzork bootstrap can model
> exits however its own translated code reads them. There is no "bridge between
> two models"; it's a generator choice. See below.

## XZIP exit-table emission — 2026-06-06 (session 2, cont.)

Beyond Zork reads every exit as a **per-direction property on the room** holding
a Z-machine word-table: `<GETP ,HERE ,P?EAST>` → table; `<GET tbl ,XTYPE>` →
kind/len word; `<GET tbl ,XROOM>` → destination. The generator now emits exits
in exactly that form for the XZIP dialect, so `MARK-EXITS`, movement, and the
auto-map read them natively. All importer work, game-agnostic, **EZIP
byte-identical** (252 tests pass). Three pieces landed:

1. **`#<radix>` numeric literals (parser).** `<CONSTANT CONNECT #2 001000000000>`
   tokenized as the atom `#2` + decimal `1000000000`, so the exit-**kind**
   constants were never seeded. A token post-pass in `parser.py` folds
   `#<radix> <digits>` → `int(digits, radix)`. Now `CONNECT`=512, `SCONNECT`=768,
   `FCONNECT`=1024, `DCONNECT`=1280, `SORRY-EXIT`=1536, … seed correctly (and any
   other binary literal across the game). Game-agnostic; `tests/test_parser.py`.

2. **Direction-property `XTYPE` tables (generator).** New `exit_tables` dialect
   knob on `GameConfig` (set on `BEYONDZORK_CONFIG`). For XZIP rooms, `_gen_exits`
   also sets a property per direction holding `[XTYPE|len, XROOM, XDATA]`, mapping
   the cases `_parse_exit` already distinguishes: `<TO>`→CONNECT, `<SAY-TO>`→
   SCONNECT (+message at XDATA), `<PER>`→FCONNECT, `<SORRY>`→SORRY-EXIT, blocked→
   NO-EXIT. The EZIP exit objects are still emitted (substrate `go` keeps
   working). Live: Hilltop now has `east=[769, <Cove>, 'You amble down the
   hill.']`, `nw=[513, <Edge of Storms>]`, `down=[1025, 'EXIT-A-TREE']`.

3. **`P?<dir>` numbering (reset body).** The `P?` direction constants are
   compiler-intrinsic (absent from source); seeded as consecutive descending
   integers (`north`=12…`down`=3, `in`/`out` below) in
   `_beyondzork_reset_state_body.py` so `MARK-EXITS`'s numeric `DLESS?` loop runs.

**Result:** `look` now runs **past `MARK-EXITS` and `describe_here`** (no error in
either) and reaches **`DISPLAY-PLACE`** — the auto-map renderer — which next
fails on `intbl_p` (`INTBL?`, table search). So exit representation is done; the
remaining work is the **auto-map renderer + character/display zstate**:
`DISPLAY-PLACE`/`NEW-MAP`/`IBM-BOX`, `ROOMS-MAPPED`/`OLD-HERE`, and `getp`-by-
*variable* (`<GETP ,HERE DIR>` currently mis-emits `getp("dir")` literal — a
runtime `P?`-number→direction-name resolver is needed for the map to mark real
exits). That `getp`-by-variable fix + the map renderer is the next task.

## Auto-map renderer, Stage 1 — builtins — 2026-06-06 (session 2, cont.)

The renderer (`DISPLAY-PLACE` → `new_map`/`draw_map`/`show_map`/`ibm_box`/
`do_curset` + `setup_dbox`/`justify_dbox`/`display_dbox` + the sline painters)
hit a wall of undefined ZIL builtins. Stage 1 implements them — all standard
ZIL/Z-machine ops, game-agnostic, EZIP byte-identical (254 tests pass):

- **Handlers** in `translator/expr_handlers.py`: `INTBL?`→`_.intbl_p`,
  `COPYT`→`_.copyt`, `PRINTT`→`_.printt`, `PUTB`→`_.table_put`, `GETPT`→`getp`
  (a table-valued property is the table in our model), `FONT`→no-op (we render
  font-3 glyphs as Unicode), `INC`/`DEC`→walrus mutate `(x := x ± 1)`.
- **Substrate verbs** in `verbs/system/tables.py`: `intbl_p` (linear search →
  matching sub-table or `False`), `copyt` (slot copy, negative = backward),
  `printt` (emit a byte grid to the window). All guard `None`/empty so they're
  safe before the Stage-2 tables exist.

`look` now runs through every renderer builtin and into the **data**-dependent
geometry, where it fails with `TypeError` because `DWIDTH` (and its cohort) are
unseeded placeholder strings (`"NUMBER"`). So the builtin wall is cleared; the
remaining work is purely **data**, in two parts:

- **Stage 2 — static display tables (`Tables: 0`).** `MAP`, `ROOMS-MAPPED`,
  `SLINE`, `DBOX`, `NXCHARS`/`XCHARS`/`MCHARS`, `SETOFFS`, `SNAMES`,
  `XOFFS`/`YOFFS`, `PDIR-LIST` — the XZIP `<ITABLE>`/`<TABLE>` extractor drops
  these. Also the `getp`-by-expression fix + `P?`-number→name resolver and a
  faithful byte-addressed table/pointer model (`REST`/`INTBL?`/`COPYT` currently
  copy list slices, not in-place views) so the buffer-scrolling routines work.
- **Stage 3 — runtime display globals.** `WIDTH`/`HEIGHT`/`CWIDTH`/`CHEIGHT`/
  `DWIDTH`/`MAPX`/`MAPY`/`CENTERX`/`CENTERY`/`DMODE`/`PRIOR`/`VT220` + the IBM
  box glyphs — normally computed by `INITVARS`/`SETUP-CHARACTER` from the
  Z-machine header. Seed window-matched values in the reset body (or run the
  init routines). Plus the general `<APPLY ,MAP-ROUTINE …>` routine-value
  dispatch (in `draw_map`), reached only once the geometry is seeded.

Stage 1 makes the renderer *run*; Stages 2-3 make it *render correctly*.

## Stages 2 + 3 — table extraction + runtime globals — 2026-06-06 (session 3)

Stages 2 and 3 largely landed. `look` now runs the **entire describe path** end to
end — room title, the **exits status line paints** into the top window
(`Hilltop … :9`), the full room/object listing runs — and on into the DBOX
auto-map renderer. All importer work, game-agnostic, **265 tests pass** (was 254);
the consistency + leakage suites pass against freshly-regenerated zork1 **and** hhg.

The breakthrough was one root-cause parser fix that cascaded:

1. **ZIL DECL stripping (`parser.py`).** `<GLOBAL DWIDTH:NUMBER 0>` tokenised as
   `DWIDTH` + a *phantom* `NUMBER` atom (the `:` was dropped), so the type name
   landed in the value slot — every typed global seeded the literal string
   `"NUMBER"`/`"FLAG"`/`"TABLE"` instead of its real value (this was the `DWIDTH`
   TypeError). The tokenizer now absorbs the `:TYPE` DECL into the atom and
   `parse()` strips it. EZIP uses **zero** colon-DECLs (zork1/2/3) so its output is
   untouched; hhg uses none either.

2. **Compile-time expression evaluator + ITABLE/CONSTANT-table extraction
   (`converter.py`).** With (1) fixed, `<GLOBAL NAME:TABLE <ITABLE …>>` and
   `<CONSTANT NAME <ITABLE/PTABLE …>>` forms became visible. Added `_eval_const_expr`
   (variadic `+ - * /` over earlier constants — `%<* ,MWIDTH ,MHEIGHT>` → 187) and
   `_extract_itable_values` (zero-filled buffers at a resolved symbolic length).
   **Tables jumped 10 → 225**; every renderer table now seeds (`MAP`, `SLINE`,
   `DBOX`, `ROOMS-MAPPED`, `SETOFFS`, `SNAMES`, `XOFFS`/`YOFFS`, `PDIR-LIST`,
   `AUX-TABLE`, `GOOD-DIRS`, …) and the geometry constants resolve (`CENTERX`=8,
   `MAP-SIZE`=187, `DBOX-LENGTH`=1552). Also seeds zork2 (+13) / zork3 (+25) /
   hhg (+10) ITABLEs that were silently dropped before — a strict improvement; the
   consistency suite (verb-metadata only) stays green. *Watch:* a dropped ITABLE
   global was `None` (falsy) and is now a real `[0]*n` (truthy) — correct ZIL
   semantics, but re-run zork smoke if anything looks off.

3. **Runtime display geometry (reset body).** `_beyondzork_reset_state_body.py`
   now seeds the values `INITVARS`/`SETUP-CHARACTER` would compute from the
   (absent) Z-machine header: `CWIDTH=CHEIGHT=1` (puts `DO-CURSET` in its
   cell-addressed branch), `WIDTH=80`/`HEIGHT=24`, `DWIDTH=BOXWIDTH=60`,
   `DHEIGHT=MAX-DHEIGHT=9`, `MOUSEDGE`/`SWIDTH`/`BARWIDTH`, `VT220=True`, `HOST=0`
   (neutral — dodges the Apple/Mac/IBM special paths). The IBM box glyphs are
   remapped from CP437 codepoints to the **Unicode box-drawing block**
   (`IBM-TLC`→┌ etc.) so the frame paints as a real box through the Rich pipeline.

Plus four translator gaps the deeper path hit, each game-agnostic:

- **`MAKE`/`UNMAKE`** (`stmt_handlers.py`) — Beyond Zork's `macros.zil` defines
  them as `<FSET>`/`<FCLEAR>`; delegate to those handlers.
- **`ASSIGNED?`** (`expr_handlers.py`) — `<ASSIGNED? .OPT>` → `(var is not None)`
  (unsupplied optional params default to None). Also fixes a latent NameError in
  zork2/zork3/hhg.
- **`FIRST?`/`NEXT?` coerce empty → ZIL FALSE (`0`), XZIP dialect only**
  (`expr_handlers.py` emits `(… or 0)` when `game_config.exit_tables`). The XZIP
  object-walk loops terminate on `<ZERO? .OBJ>` / `== 0`, and `.first()` /
  `next_sibling` return `None`, which `!= 0` — so the loops ran off the end into
  `None.flag()`. **Gating is essential:** an earlier un-gated version (coercing for
  all games + returning `0` from the shared `next_sibling` substrate) **regressed
  zork1 smoke 242 → 80** (the troll combat stopped resolving). EZIP loops use
  truthy / `is None` tests that already handle `None`, so they keep the plain
  form; the `next_sibling` substrate stays game-neutral (`return None`). Verified:
  zork1's regenerated verbs are byte-identical to baseline (only a docstring
  differs in `movement.py`). **Lesson: never change a shared substrate return or
  an ungated translator handler without a zork1-smoke before/after — the
  consistency suite checks verb metadata, not runtime behaviour.**
- **`<APPLY routine-var ,M-clause>` substrate** (`verbs/system/apply.py` +
  `_h_apply` fallback) — when the routine arrives through a variable
  (`<SET X <GETP ,HERE ,P?ACTION>> <APPLY .X ,M-LOOK>`) the inline handler can't
  match it; route to `_.apply`, which does the HERE-relative M-* dispatch (M-LOOK →
  the room's `look` verb) and safely no-ops otherwise (Python 3 removed `apply`).

**Remaining blocker — the byte-addressed table/pointer model.** `look` now fails
in `JUSTIFY-DBOX` on `base + (line * BOXWIDTH)` where `base` is a list: the
buffer-scroll routines (`JUSTIFY-DBOX`, `CENTER-SLINE`, `SETUP-DBOX`,
`DISPLAY-DBOX`) do real Z-machine **pointer arithmetic** — `<+ .BASE off>`,
`<- .PTR .BASE>`, pointer comparisons, and `PUTB`/`COPYT` through a `REST` view
that must mutate the *original* backing table. Our model stores tables as JSON
list properties and `REST` returns a slice (copy), so pointer math and in-place
mutation don't work. This is the "faithful byte-addressed table/pointer model"
flagged from the start — the last hard piece, and a distinct sub-project:

- A pointer/view type returned by `REST`/`INTBL?` holding `(backing_list, offset)`
  with `+`/`-`/comparison and `table_get`/`table_put`/`copyt` operating through it.
- Open question: in-place mutation must persist on the stored zstate prop within a
  turn (does `get_property` return a live mutable list or a fresh deserialization?).
  Resolve before building the view, or writes to `DBOX`/`SLINE` won't stick.

Everything up to the DBOX justifier renders; sequence the pointer model next, then
visually verify the map + status line over interactive SSH / the GMCP `Window.*`
capture harness.

## Byte-addressed pointer model — `look` completes — 2026-06-06 (session 4)

The pointer model landed and **`look` now runs end-to-end with zero tracebacks** —
describe path, status line, DBOX auto-map, and the buffer-scroll pointer
arithmetic all execute; navigation works (Hilltop ↔ Cove ↔ back). 268 tests pass;
EZIP generated verb code is unchanged (gated). Two commits — a core scratch dict
(django-moo) and the importer side (moo-agent).

**Design — integer addresses, not a pointer class.** ZIL emits `<+ .BASE off>` as
plain Python `base + off`, so a pointer must support native `+`/`-`/comparison.
A custom class would fight RestrictedPython's attribute guards and has no
Rule-Zero-clean home, so **a pointer is a plain int address**. A per-task
registry lays each table out at a non-overlapping base; resolving an address maps
it to `(backing_list, offset)`. Ints make all the translated arithmetic/compares
work for free.

1. **Core scratch dict (django-moo, blessed as game-neutral).** A generic
   `scratch` contextvar + `ContextManager.get_scratch()` + a read-only
   `context.scratch` SDK descriptor (returns the mutable dict). Lifecycle matches
   the existing perm/verb/prop caches (fresh per session, reset on `__exit__`).
   No ZIL concepts in core — it's generic per-task storage; the registry lives in
   it. **This is the one core change this arc; authorized explicitly.**
2. **`zaddr_*` substrate (`verbs/system/ztables.py`).** `zaddr_rest`/`zaddr_get`/
   `zaddr_put`/`zaddr_copyt`/`zaddr_intbl_p`, polymorphic over a list (a table
   value straight from `zstate_get`/`getp`) or an int address. Cell-indexed (byte
   for the `(BYTE)` ITABLE buffers these routines use). Mutation is in place and
   persists within the turn because `get_property` has a **session cache** that
   returns the same list object across the verb calls in one `look` (the buffers
   are rebuilt each turn, so no cross-turn write-back is needed). Address 0 stays
   ZIL FALSE so `INTBL?` returns 0 for "not found".
3. **Translator gating.** REST/GET/GETB/PUT/PUTB/COPYT/INTBL? → `zaddr_*` under
   the XZIP dialect (`game_config.exit_tables`); EZIP keeps the list-based
   primitives verbatim. (Helper names in the substrate must be non-`_`-prefixed —
   RestrictedPython rejects leading underscores.)
4. **`LOWCORE` → `_.lowcore` (`verbs/system/zmachine.py`).** `<LOWCORE field>`
   reads the absent Z-machine header; returns the benign baseline 0 (FLAGS bit
   tests then take the safe default). Only Beyond Zork emits LOWCORE.

**Remaining = visual fidelity, not crashes.** The raw `shell -c` drive shows the
DBOX as `\x00` cells (the byte buffer painted to the window region as NUL =
empty); the box-drawing frame, the room description inside it, and the font-3 map
glyphs only render under an **interactive rich-mode SSH session** (raw-mode
harnesses no-op the window `Application`) or the planned **GMCP `Window.*` capture
harness**. Next: drive `look`/movement over real SSH (or the GMCP harness),
confirm the box + stats line + auto-map paint, and tune any byte/word or
cell-offset details that surface (the cell-addressed model is exact for the byte
buffers; word-table REST in non-DBOX routines like `lower_sline` is approximate
and may need per-table width if the exits line looks off).
