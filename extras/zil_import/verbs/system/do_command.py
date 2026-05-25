#!moo verb do_command --on "System Object"
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
LambdaMOO ``$do_command`` pre-dispatch hook for ZIL games.

Called by ``moo/core/parse.py:interpret()`` before normal verb dispatch.

Responsibilities (in dispatch order):

1.  ``again`` / ``g`` repeat-last-command via ``zstate_last_command``.
2.  Per-turn daemon tick (``i-river`` drift, ``i-lantern`` dim, …).
3.  Forwarding to ``preturnfunc`` (ZIL M-BEG) on the player's location
    and on any underlying physical room when the location is a vehicle.
4.  Late dobj resolution — see ``resolve_dobj_late.py``.
5.  Multi-object dispatch (``take all`` / ``drop A and B``) — see
    ``dispatch_multi.py``.

Helpers extracted to sibling System Object verbs:

* ``rehydrate_preps`` / ``dehydrate_preps`` — see ``again_state.py``.
* ``split_multi`` / ``gather_takeables`` — see ``take_helpers.py``.
* ``peek_into`` — see ``peek_into.py``.
* ``resolve_dobj_late`` — see ``resolve_dobj_late.py``.
* ``dispatch_multi`` — see ``dispatch_multi.py``.

:param args[0]: The verb word the player typed.
:returns: ``True`` to short-circuit normal dispatch; ``False`` /
    falsy to let the parser proceed to verb resolution.
"""

import re

from moo.sdk import context, NoSuchObjectError, NoSuchPropertyError, lookup


player = context.player
parser = context.parser
verb_word = (args[0] if args else "").lower()
is_again = verb_word in ("again", "g")

# Strip trailing sentence punctuation (.?!) from the verb word and the
# final word of the parser command so ``look.``, ``inventory!``, and a
# bare ``.`` don't tokenize into nonsense verbs.  Canonical Zork strips
# trailing punctuation before lookup; we replicate the cheap variant
# here at the do_command layer (the moo-core parser tokenizer is
# Rule-Zero territory).
if verb_word and verb_word[-1] in ".?!":
    stripped = verb_word.rstrip(".?!")
    if not stripped:
        # Bare punctuation — nothing to dispatch.
        return True
    verb_word = stripped
    if parser.words:
        parser.words[0] = parser.words[0].rstrip(".?!") or parser.words[0]
        # Drop any words that are now empty (bare punctuation tokens).
        parser.words = [w for w in parser.words if w]
    if parser.command:
        parser.command = parser.command.rstrip(".?!").rstrip()

# ``again`` / ``g`` — restore last command into the live parser.
if is_again:
    snap = player.getp("zstate_last_command", None)
    if not snap:
        print("You haven't done anything to repeat yet.")
        return True
    parser.command = snap.get("command", "")
    parser.words = list(snap.get("words") or [])
    parser.dobj_str = snap.get("dobj_str")
    parser.dobj_spec_str = snap.get("dobj_spec_str")
    dpk = snap.get("dobj_pk")
    if dpk is not None:
        try:
            parser.dobj = lookup(int(dpk))
        except NoSuchObjectError:
            parser.dobj = None
    else:
        parser.dobj = None
    parser.prepositions = _.rehydrate_preps(snap.get("preps") or {})
    verb_word = parser.words[0].lower() if parser.words else ""

loc = player.location
if loc is None:
    return False

# ZIL ``<BUZZ ...>`` words (A AN THE IS ARE AM AND OF THEN ...) are dropped
# by the Z-machine parser before verb dispatch.  DjangoMOO's tokenizer keeps
# them, so ``i am ford`` parses with words=[i, am, ford] and the ``i``
# dispatcher doesn't see ``ford`` as a clean dobj.  Strip BUZZ words from
# parser.words[1:] (preserving the verb), then re-resolve the dobj from the
# trimmed tail.  Only fires when at least one buzz word would be dropped.
if len(parser.words) > 1:
    BUZZ_WORDS = {"a", "an", "the", "is", "are", "am", "and", "of", "then"}
    kept = [parser.words[0]]
    dropped_any = False
    for word in parser.words[1:]:
        if word.lower() in BUZZ_WORDS:
            dropped_any = True
            continue
        kept.append(word)
    if dropped_any and len(kept) >= 2:
        parser.words = kept
        parser.command = " ".join(kept)
        # Re-resolve dobj from the trimmed tail.  Use player.find() then
        # loc.find() so scenery items resolve via the same paths as the
        # normal parse.  Skip when the parser already bound a dobj (the
        # buzz word was extraneous noise around an already-good parse).
        if parser.dobj is None and len(kept) >= 2:
            tail = " ".join(kept[1:])
            candidate = player.find(tail).first()
            if candidate is None:
                candidate = loc.find(tail).first()
            if candidate is not None:
                parser.dobj = candidate
                parser.dobj_str = tail
            elif not parser.dobj_str:
                parser.dobj_str = tail

# Bare ``drop`` / ``pour`` / ``spill`` (no dobj) — canonical dispatch
# routes these through the LEAVE dispatcher (they're aliases) and into
# V-LEAVE, which walks the OUT exit and prints "You can't go that way."
# from inside ``walk``.  Intercept before the misdispatch and ask the
# player to name an object instead.
if len(parser.words) == 1 and parser.words[0].lower() in ("drop", "pour", "spill") and not parser.has_dobj_str():
    print("What do you want to " + parser.words[0].lower() + "?")
    return True

# Bare ``disembark`` / ``unboard`` — substrate is ``--dspec this`` so
# missing-dobj makes the parser bail with "I don't know how to do that."
# Canonical Zork accepts the bare form by auto-targeting the player's
# current vehicle.  If the player is sitting inside a vehicle, inject
# it as the dobj so the substrate disembark verb dispatches normally.
if len(parser.words) == 1 and parser.words[0].lower() in ("disembark", "unboard") and not parser.has_dobj_str():
    loc = player.location
    if loc is not None and loc.getp("vehicle", False):
        parser.dobj = loc
        parser.dobj_str = loc.name or ""

# Bare transitive verbs whose substrate is ``--dspec this`` — the parser
# refuses to dispatch without a dobj and the player sees "I don't know
# how to do that." Print a canonical "What do you want to X?" instead.
if len(parser.words) == 1 and not parser.has_dobj_str():
    BARE_DOBJ_PROMPTS = {
        "take": "What do you want to take?",
        "get": "What do you want to take?",
        "grab": "What do you want to take?",
        "open": "What do you want to open?",
        "close": "What do you want to close?",
        "shut": "What do you want to close?",
        "examine": "What do you want to examine?",
        "x": "What do you want to examine?",
        "describe": "What do you want to examine?",
        "give": "Give what to whom?",
        "donate": "Give what to whom?",
        "offer": "Give what to whom?",
        "feed": "Give what to whom?",
        "throw": "What do you want to throw?",
        "hurl": "What do you want to throw?",
        "toss": "What do you want to throw?",
        "eat": "What do you want to eat?",
        "drink": "What do you want to drink?",
        "wear": "What do you want to wear?",
        "read": "What do you want to read?",
        "attack": "What do you want to attack?",
        "kill": "What do you want to attack?",
        "break": "What do you want to break?",
    }
    word = parser.words[0].lower()
    if word in BARE_DOBJ_PROMPTS:
        print(BARE_DOBJ_PROMPTS[word])
        return True

# ``give to <iobj>`` (and offer/donate aliases) — dobj is missing but the
# preposition is present.  Canonical "Give what to whom?" beats
# "I don't know how to do that."
if (
    len(parser.words) >= 2
    and parser.words[0].lower() in ("give", "donate", "offer")
    and not parser.has_dobj_str()
    and parser.prepositions
    and "to" in parser.prepositions
):
    print("Give what to whom?")
    return True

# Rewrite ``throw <weapon> at <actor>`` (and hurl / chuck / toss
# aliases) into the canonical ``attack <actor> with <weapon>`` form.
# Canonical ZIL has ``<SYNTAX THROW OBJECT AT OBJECT = V-ATTACK>`` but
# the generated parser routes the ``at`` preposition through V-PUT
# (which rejects with "You can't put things in the troll."); the throw
# is lost entirely.  Rewrite before dispatch when the iobj is an
# actorbit object so the combat path runs cleanly.
if len(parser.words) >= 4 and parser.words[0].lower() in ("throw", "hurl", "chuck", "toss") and parser.dobj_str:
    preps = parser.prepositions or {}
    at_iobj = None
    if "at" in preps and preps["at"]:
        entry = preps["at"][0]
        if len(entry) >= 3:
            at_iobj = entry[2]
    if at_iobj is not None and at_iobj.flag("actorbit"):
        # Build the rewritten command.  Use the resolved iobj's name for
        # the new dobj_str so subsequent dobj resolution finds it.
        actor_name = at_iobj.name or ""
        weapon_str = parser.dobj_str
        # The original dobj was the weapon (a Thing) — preserve the
        # resolved object reference into the rewritten ``with`` slot so
        # the attack verb sees a populated iobj without re-resolving.
        weapon_obj = parser.dobj
        new_command = "attack " + actor_name + " with " + weapon_str
        parser.words = new_command.split()
        parser.command = new_command
        parser.dobj_str = actor_name
        parser.dobj = at_iobj
        parser.dobj_spec_str = ""
        parser.prepositions = {"with": [["", weapon_str, weapon_obj]]}
        verb_word = "attack"

# Rewrite ``turn off <X>`` / ``turn <X> off`` / ``turn on <X>`` /
# ``turn <X> on`` into the canonical extinguish/light verb the parser
# already routes correctly.  Canonical Zork ZIL doesn't have a "turn
# off" syntax — players are expected to type ``extinguish lantern`` —
# but everyone tries ``turn off lantern`` first, so meet the player
# halfway by rewriting before parser dispatch.
#
# ``turn off lantern`` parses as words=[turn,off,lantern] with
# dobj_str=None and prepositions={off: [['', 'lantern', <obj>]]} because
# the parser treats ``off`` as a preposition.  Reach into prepositions
# to grab the already-resolved object.
if len(parser.words) >= 2 and parser.words[0].lower() == "turn":
    new_verb = None
    new_dobj = None
    resolved_obj = None
    preps = parser.prepositions or {}
    # turn off <X> / turn on <X> — preposition shape.
    for prep_name, target in (("off", "extinguish"), ("on", "light")):
        if prep_name in preps and preps[prep_name]:
            entry = preps[prep_name][0]
            if len(entry) >= 2 and entry[1]:
                new_verb = target
                new_dobj = entry[1]
                resolved_obj = entry[2] if len(entry) >= 3 else None
                break
    # turn <X> off / turn <X> on — postposition (parser may not catch this).
    if new_verb is None and len(parser.words) >= 3:
        w_last = parser.words[-1].lower()
        if w_last == "off":
            new_verb = "extinguish"
            new_dobj = " ".join(parser.words[1:-1])
        elif w_last == "on":
            new_verb = "light"
            new_dobj = " ".join(parser.words[1:-1])
        # Postposition path: parser already resolved the middle word as dobj.
        if new_verb is not None and parser.dobj is not None:
            resolved_obj = parser.dobj
    if new_verb is not None and new_dobj:
        parser.words = [new_verb] + new_dobj.split()
        parser.command = new_verb + " " + new_dobj
        parser.dobj_str = new_dobj
        parser.dobj = resolved_obj
        parser.prepositions = {}
        verb_word = new_verb

# Rewrite compound ``look <prep> <X>`` into the canonical substrate verb
# the parser routes correctly.  The Actor's ``look`` dispatcher
# already has a compound table but loses dispatch to the room's M-LOOK
# (``--dspec either``, last-match-wins).  Rewriting at the do_command
# layer sidesteps that ordering entirely.
#
# Canonical preposition forms (after parser canonicalization):
#     at      → examine
#     in      → look_inside  (also "inside", "into", "within")
#     on      → look_on      (also "onto", "upon", "above")
#     under   → look_under   (also "underneath", "beneath", "below")
#     behind  → look_behind  (also "past")
if (
    len(parser.words) >= 2
    and parser.words[0].lower() == "look"
    and parser.words[1].lower()
    in (
        "at",
        "to",
        "in",
        "inside",
        "into",
        "within",
        "on",
        "onto",
        "upon",
        "above",
        "under",
        "underneath",
        "beneath",
        "below",
        "behind",
        "past",
        "out",
        "through",
    )
):
    LOOK_PREP_TO_VERB = {
        "at": "examine",
        "in": "look_inside",
        "on": "look_on",
        "under": "look_under",
        "behind": "look_behind",
    }
    # ZIL ``<SYNTAX LOOK OUT OBJECT = V-LOOK-INSIDE>`` and ``LOOK THROUGH OBJECT
    # = V-LOOK-INSIDE`` use words the canonical parser doesn't register as
    # prepositions (``out`` only appears as part of ``out of``, ``through`` not
    # at all).  Strip them off the words list when present so the rewrite below
    # treats ``look out window`` the same as ``look in window``.
    LOOK_WORD_PARTICLES = ("out", "through")
    new_verb = None
    new_dobj = None
    resolved_obj = None
    preps = parser.prepositions or {}
    for prep_name, target in LOOK_PREP_TO_VERB.items():
        if prep_name in preps and preps[prep_name]:
            entry = preps[prep_name][0]
            if len(entry) >= 2 and entry[1]:
                new_verb = target
                new_dobj = entry[1]
                resolved_obj = entry[2] if len(entry) >= 3 else None
                break
    if new_verb is None and parser.words[1].lower() in LOOK_WORD_PARTICLES and len(parser.words) >= 3:
        new_verb = "look_inside"
        new_dobj = " ".join(parser.words[2:])
        candidate = player.find(new_dobj).first()
        if candidate is None and loc is not None:
            candidate = loc.find(new_dobj).first()
        resolved_obj = candidate
    if new_verb is not None and new_dobj:
        parser.words = [new_verb] + new_dobj.split()
        parser.command = new_verb + " " + new_dobj
        parser.dobj_str = new_dobj
        parser.dobj = resolved_obj
        parser.prepositions = {}
        verb_word = new_verb

# Run GO (the canonical Zork session-bootstrap routine) on the player's
# first command of the session.  GO queues the always-on daemons
# (i-fight, i-sword, i-thief, i-candles, i-lantern), sets HERE / LIT,
# and prints the welcome banner.  Without this hook, a fresh connection
# never gets those daemons scheduled and the lantern / candles never
# burn out, the sword never glows near grues, and the thief never
# patrols.  Tracked per-player via ``zstate_started`` so each connect
# fires GO exactly once.
#
# Use the ``zil_init`` shim (see verbs/thing/helpers/zil_init.py)
# rather than ``go`` directly: invoke_verb("go") collides with V-WALK-
# AROUND's ``go`` alias and prints "Use compass directions for movement."
# instead of running the GO body.  The shim skips the look / main_loop
# parts of GO (handled by do_command's normal dispatch and the shell
# read loop respectively) and only does daemon scheduling.
if not player.getp("zstate_started", False):
    player.set_property("zstate_started", True)
    zthing = _.get_property("thing")
    if zthing is not None and zthing.has_verb("zil_init"):
        try:
            zthing.invoke_verb("zil_init")
        except Exception:  # pylint: disable=broad-except
            # GO failure must not block the player's first command.
            # Reset the flag so the next command retries.
            player.set_property("zstate_started", False)

# Tick the queue FIRST so per-turn daemons fire before preturnfunc and main
# dispatch — lets a vehicle's drift land before the player's command runs.
_.tick()

# i-river may have moved the boat (and player with it) during tick.
loc = player.location
if loc is None:
    return False
is_vehicle = bool(loc.getp("vehicle", False))

player_verb_arg = parser.words[0] if parser.words else None

if is_vehicle:
    if loc.has_verb("preturnfunc"):
        if loc.invoke_verb("preturnfunc", "M-BEG", player_verb_arg):
            return True
    physical_room = loc.location
else:
    physical_room = loc

if physical_room is not None and physical_room.has_verb("preturnfunc"):
    if physical_room.invoke_verb("preturnfunc", "M-BEG", player_verb_arg):
        return True

# Pronoun resolution — replace ``it`` / ``him`` / ``her`` in dobj_str
# with the player's last-resolved dobj when it's still in scope.  Run
# BEFORE resolve_dobj_late so the late-resolver sees the rewritten
# dobj_str.  Canonical ZIL sets P-IT-OBJECT after each successful
# dobj resolution; we replicate that via zstate_pronoun_it on the
# player.
_.resolve_pronoun(parser, player, loc)

# The parser reads ``self.dobj`` inside ``get_search_order`` *after*
# ``__init__`` returns, so mutating it here is well-defined: the dobj we
# set will appear in the verb-dispatch search order naturally.
_.resolve_dobj_late(parser, player, loc, physical_room, is_vehicle)

# Per-room (PSEUDO ...) scenery: when the dobj didn't resolve and the
# typed word matches a pseudo-scenery entry on the current room, invoke
# the named routine on Thing.  ZIL's PSEUDO declares phantom scenery
# words that dispatch to a routine — canonical use is single-verb
# scenery like ``climb tree`` (TREE-PSEUDO handles climb-up).  The
# pseudo map is emitted by the generator as
# ``{word_lower: routine_snake_name}``.
#
# After the pseudo runs, decide whether to fall through to a default
# message.  Heuristic: inspect the pseudo verb's source for the
# player's verb word — if it's present, assume the pseudo handled
# the verb and skip the default.  Otherwise emit
# "There's nothing special about the <word>." (Z-machine's default
# scenery response) so the player doesn't see a silent prompt.
if parser.dobj is None and parser.dobj_str and physical_room is not None:
    try:
        pseudo_map = physical_room.get_property("pseudo") or {}
    except NoSuchPropertyError:
        pseudo_map = {}
    pseudo_routine = pseudo_map.get(parser.dobj_str.lower())
    if pseudo_routine:
        zthing = _.get_property("thing")
        if zthing is not None and zthing.has_verb(pseudo_routine):
            # Inspect the pseudo verb's source to decide whether to fall
            # through to a default "nothing special" message.  Heuristic:
            #   1. If the source unconditionally prints (no VERB? gate),
            #      trust it — it always handles the command.
            #   2. Else if the player's verb word appears in the source,
            #      assume the verb is handled in one of the branches.
            #   3. Otherwise fall through to "nothing special" so the
            #      player doesn't see a silent prompt for verbs the
            #      pseudo doesn't handle (most commonly: examine on a
            #      pseudo that only handles climb-up).
            #
            # Many PSEUDOs register the same routine name on Thing
            # (UNIMPORTANT-THING-F covers every "scenery" item), so
            # get_verb is ambiguous.  Treat ambiguity as "trust the
            # pseudo" — these shared routines are unconditional handlers
            # by convention (the bedroom-sink case prints "That's not
            # important; leave it alone." for every verb).
            handles_verb = True
            try:
                pseudo_verb = zthing.get_verb(pseudo_routine)
                pseudo_source = pseudo_verb.code or ""
                verb_word = parser.words[0].lower() if parser.words else ""
                unconditional_print = (
                    "the_player_verb" not in pseudo_source and "invoked_verb_name" not in pseudo_source
                )
                # Word-boundary match: surround with non-identifier chars to
                # avoid spurious substring hits.  `climb` should NOT match
                # `'climb-up'` (TREE-PSEUDO checks `climb-up`/`climb-foo`,
                # not bare `climb`).  Use a quoted-literal check ('verb' /
                # "verb") so the verb_word matches only when the source
                # actually compares against it as a discrete string.
                if verb_word:
                    pattern = r"['\"]" + re.escape(verb_word) + r"['\"]"
                    quoted_match = bool(re.search(pattern, pseudo_source))
                else:
                    quoted_match = False
                handles_verb = unconditional_print or quoted_match
            except Exception:  # pylint: disable=broad-exception-caught
                pass
            zthing.invoke_verb(pseudo_routine)
            if not handles_verb:
                print("There's nothing special about the " + parser.dobj_str + ".")
            return True

# Snapshot BEFORE the multi-object short-circuits below, so ``again`` after
# ``take all`` re-runs ``take all``.  Skip on empty verb_word and on the
# servicing-``again`` path (otherwise the snapshot is self-referential).
if not is_again and verb_word:
    try:
        snap_dobj_pk = parser.dobj.pk if parser.dobj is not None else None
        snap = {
            "command": parser.command,
            "words": list(parser.words),
            "dobj_str": parser.dobj_str,
            "dobj_spec_str": parser.dobj_spec_str,
            "dobj_pk": snap_dobj_pk,
            "preps": _.dehydrate_preps(parser.prepositions or {}),
        }
        player.set_property("zstate_last_command", snap)
        # Snapshot the resolved dobj for the next turn's pronoun
        # resolution.  Only record real Objects (skip pronouns the
        # current turn used so chained "x it" / "open it" doesn't
        # bind to itself).
        if parser.dobj is not None and parser.dobj_str not in ("it", "him", "her"):
            player.set_property("zstate_pronoun_it", parser.dobj.pk)
    except (AttributeError, TypeError):
        pass

if _.dispatch_multi(verb_word, parser, player, physical_room, loc, is_vehicle):
    return True

return False
