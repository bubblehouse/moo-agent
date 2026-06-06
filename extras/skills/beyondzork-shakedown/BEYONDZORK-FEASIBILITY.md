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
