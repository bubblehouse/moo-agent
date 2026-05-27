#!moo verb perform --on "Thing" --dspec this
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Hand-written replacement for the translator-emitted PERFORM.

Background
==========

ZIL's ``<PERFORM ,V?X ,O ,I>`` writes the three args to the parser
verb-and-object globals, runs the 5-stage action dispatch chain,
then expects the caller to ``<RTRUE>`` immediately so the caller's
own VERB? branch doesn't fire twice.  See
https://eblong.com/infocom/other/zil-course.fwf § PERFORM.

The translator-emitted version annotates the ``SETG`` of parser-state
slots as ``no-op in DjangoMOO`` and skips the mutation, then re-runs
the dispatch chain against the *original* parser context.  When an
action handler PERFORMs onto itself (HHG's ``ROBOT-PANEL-F`` PUT-ON
branch calling ``V?BLOCK-WITH`` on the same panel), the re-dispatched
body sees the same verb/PRSO/PRSI as the caller, re-takes the same
branch, and recurses until the celery task hits its time limit.

This shim implements proper PERFORM semantics: push the parser's
current dobj / iobj / verb word, install the PERFORM args, walk the
5-stage chain via :verb:`d_apply`, and restore in ``finally``.

Constraints
===========

- ``parser.dobj`` is a single Object.  Easy to swap.
- ``parser.prepositions`` is a dict ``{prep_str: [[spec, name, obj]]}``;
  iobj resolution walks every prep until one resolves.  To swap PRSI
  we install a synthetic prep mapping under ``"with"`` (the most common
  prep — semantically inert for the consumers we care about, which
  read PRSI via ``parser.get_iobj()`` without caring which prep
  carried it).
- The body of a re-dispatched handler reads ``invoked_verb_name(verb_name)``
  which returns ``parser.words[0].lower()`` when present.  We swap
  ``parser.words[0]`` to the PERFORM target so ``the_player_verb``
  matches the new verb.

The chain stops at the first truthy return (matches ZIL's ``RTRUE``
short-circuit).  ``v`` accumulates the latest non-falsy return for
the caller's final ``return v``.
"""

from moo.sdk import NoSuchObjectError, context, invoked_verb_name, lookup

player = context.player
parser = context.parser

a = args[0] if len(args) > 0 else None  # target verb atom (snake-case)
o = args[1] if len(args) > 1 else None  # new PRSO
i = args[2] if len(args) > 2 else None  # new PRSI

prior_dobj = parser.dobj if parser is not None else None
prior_dobj_str = parser.dobj_str if parser is not None else None
prior_words = list(parser.words) if parser is not None and parser.words else None
prior_prepositions = None
if parser is not None:
    prior_prepositions = {prep: [list(rec) for rec in records] for prep, records in parser.prepositions.items()}
prior_p_it = player.zstate_get("P-IT-OBJECT") if player is not None else None

try:
    if parser is not None:
        parser.dobj = o
        parser.dobj_str = o.name if o is not None else None
        if prior_words is not None:
            new_words = list(prior_words)
            new_words[0] = str(a) if a is not None else (new_words[0] if new_words else "")
            parser.words = new_words
        if i is not None:
            parser.prepositions = {"with": [["", i.name, i]]}
        else:
            parser.prepositions = {prep: [] for prep in parser.prepositions}

    if a != "go" and o is not None:
        player.zstate_set("P-IT-OBJECT", o)

    not_here_object = lookup("not_here_object")

    v = None
    # Stage 1: M-Beg (location action with M-BEG)
    if player.location is not None:
        loc_action = player.location.getp("action") if hasattr(player.location, "getp") else None
        if loc_action and (v := _.thing.d_apply("M-Beg", loc_action, "M-BEG")):
            return v

    # Stage 2: Preaction (table lookup by verb atom)
    preactions = player.zstate_get("PREACTIONS")
    if preactions is not None:
        try:
            preact = _.table_get(preactions, a)
        except Exception:  # pylint: disable=broad-except
            preact = None
        if preact and (v := _.thing.d_apply("Preaction", preact)):
            return v

    # Stage 3: PRSI (iobj-host) action — Phase 7 OBJECT-FUNCTION dispatch
    # via dispatch_object_function (looks up i.action, invokes the
    # combined callback emitted by translate_object_function_combined).
    if i is not None:
        if v := _.thing.dispatch_object_function(i, a, None, o):
            return v

    # Stage 4: PRSO (dobj-host) action — same combined-callback path.
    if o is not None and a != "go":
        if v := _.thing.dispatch_object_function(o, a, None, i):
            return v

    # Stage 5: Default V- routine (table lookup by verb atom)
    actions = player.zstate_get("ACTIONS")
    if actions is not None:
        try:
            default = _.table_get(actions, a)
        except Exception:  # pylint: disable=broad-except
            default = None
        if default and (v := _.thing.d_apply(False, default)):
            return v

    return v
finally:
    if parser is not None:
        parser.dobj = prior_dobj
        parser.dobj_str = prior_dobj_str
        if prior_words is not None:
            parser.words = prior_words
        if prior_prepositions is not None:
            parser.prepositions = prior_prepositions
    if player is not None:
        player.zstate_set("P-IT-OBJECT", prior_p_it)
