#!moo verb article --on "Thing" --dspec this
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Hand-written ARTICLE replacement — returns the article string instead
of printing it.

The auto-translated body emits ``print(' the', end='')`` /
``print(' a', end='')`` etc., which trips DjangoMOO's per-verb print
buffer: every nested ``_.thing.article(prso, True)`` call flushes
its own buffer on return, while the surrounding verb's print buffer
flushes at the very end.  The visible effect is the articles printing
before the parent's narrative text:

    the pocket fluff
     the your gown
    ...
    You can't put in when is already in!

Returning a string lets the caller concatenate inline; the translator
emits ``print(_.thing.article(prso, True), end='')`` for
``<ARTICLE ,PRSO T>``, so the result lands in the caller's print
buffer rather than triggering a sub-verb buffer flush.

Called as ``_.thing.article(obj, the)``.  Returns the
``" <article> <desc>"`` segment (with leading space, matching the ZIL
TELL convention).
"""

from moo.sdk import context, lookup

obj = args[0] if len(args) > 0 else None
the = args[1] if len(args) > 1 else None
# cap=True capitalises the article word (TELL ``CA``/``CTHE`` tokens — "A
# crevice" / "The crevice"); default lower-case ("a crevice" / "the crevice").
cap = bool(args[2]) if len(args) > 2 else False

if not obj:
    # PRSO/PRSI is the Z-machine null object — usually because the parser
    # couldn't resolve the noun the player typed (e.g. ``ask prosser
    # about bypass`` when ``bypass`` isn't a Z-object).  Fall back to the
    # raw dobj/iobj string from the parser so the canonical "isn't
    # interested in talking about <topic>" line reads naturally rather
    # than substituting "not here object".
    parser = context.parser if context is not None else None
    topic = None
    if parser is not None:
        for prep_records in parser.prepositions.values():
            for record in prep_records:
                if record[1] and record[2] is None:
                    topic = record[1]
                    break
            if topic:
                break
        if topic is None and parser.dobj is None and parser.dobj_str:
            topic = parser.dobj_str
    if topic:
        article_word = "the" if the else ("an" if topic[:1].lower() in "aeiou" else "a")
        result = " " + article_word + " " + topic
    else:
        obj = lookup("not_here_object")
        result = None
else:
    result = None
if result is None:
    if obj.flag("narticlebit"):
        result = " " + obj.desc()
    elif the:
        result = " the " + obj.desc()
    elif obj.flag("vowelbit"):
        result = " an " + obj.desc()
    else:
        result = " a " + obj.desc()
# Capitalise the first alphabetic character (after the leading space) for the
# CA/CTHE tokens; the leading space matches the ZIL TELL convention.
if cap and len(result) > 1:
    result = result[:1] + result[1:2].upper() + result[2:]
return result
