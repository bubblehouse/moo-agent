#!moo verb describe_object --on "Thing" --dspec this
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Hand-written DESCRIBE-OBJECT replacement.

The auto-translator emits hardcoded ``"A "`` literals before the object
desc, producing ungrammatical inventory listings like ``A ancient map``
and ``A egg``.  This replacement preserves the canonical ZIL logic but
swaps the literals for a vowel-aware article: ``An`` when the desc
starts with a vowel sound, ``A`` otherwise.
"""

from moo.sdk import context

player = context.player
obj = args[0] if len(args) > 0 else None
v_p = args[1] if len(args) > 1 else None
level = args[2] if len(args) > 2 else None
str_v = 0
av = 0


def article_for(name):
    return "An " if name[:1].lower() in ("a", "e", "i", "o", "u") else "A "


player.zstate_set("DESC-OBJECT", obj)
if level == 0 and (
    obj.invoke_verb("descfunc") if obj is not None and obj.has_verb("descfunc", recurse=False) else None
):
    return True
elif level == 0 and (
    (not obj.flag("touchbit") and (str_v := obj.getp("first_description"))) or (str_v := obj.getp("description"))
):
    print(str_v, end="")
elif level == 0:
    print("There is " + article_for(obj.desc()).lower() + obj.desc() + " here", end="")
    if obj.flag("onbit"):
        print(" (providing light)", end="")
    print(".", end="")
else:
    print(_.table_get(player.zstate_get("INDENTS"), level) + article_for(obj.desc()) + obj.desc(), end="")
    if obj.flag("onbit"):
        print(" (providing light)", end="")
    elif obj.flag("wearbit") and obj.location == player:
        print(" (being worn)", end="")
_.thing.null_f()
if level == 0 and (av := player.location) and av.flag("vehicle"):
    print(" (outside the " + av.desc() + ")", end="")
print()
if _.thing.is_see_inside(obj) and obj.contents.first():
    return _.thing.print_cont(obj, v_p, level)
