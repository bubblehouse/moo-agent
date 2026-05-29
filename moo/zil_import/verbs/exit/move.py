#!moo verb move --on "Exit"
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module

"""
Zork-specific exit traversal.

Replaces movement.py's ``walk`` dispatcher so per-exit overrides for
conditional, per-routine, and door variants can live as ``move`` verbs
on individual exit Objects.  The contract mirrors native
``$exit.move``: ``args[0]`` is the entity being moved.  The vehicle
case (boat) is handled by ``current_vehicle`` so the entire vehicle
relocates while the player stays inside it.

Property contract on the exit Object:

* ``source`` — origin room.
* ``dest`` — destination room (``None`` means routine-driven or blocked).
* ``nogo_msg`` — printed when ``dest`` is missing or condition fails.
* ``message`` — printed on successful traversal.
* ``exit_routine`` — verb name on ``$thing`` returning ``dest`` (or ``None``).
* ``condition_flag`` — gates traversal.  Resolution order:
  ``FALSE-FLAG`` (always false); per-player zstate; object lookup by
  snake-cased atom name reading its ``open`` property.  ``None`` /
  missing → unconditional.

:param args[0]: The entity being moved (typically ``context.player``).
"""

from moo.sdk import context, lookup, NoSuchObjectError


def print_nogo(reason: str) -> None:
    """
    Print this exit's ``nogo_msg`` or a default block message.

    :param reason: Informational tag for future logging hooks
        (e.g. ``"condition"``, ``"routine"``); fallback text is the
        same in either case.
    """
    nogo_msg = this.getp("nogo_msg", None)
    if nogo_msg:
        print(nogo_msg)
        return
    if reason == "routine":
        # exit_routine returned None — the routine printed its own message.
        if this.getp("exit_routine", None):
            return
    print("You can't go that way.")


def evaluate_condition():
    """
    Resolve ``condition_flag``.

    :returns: ``True`` iff the exit is passable.
    """
    flag = this.getp("condition_flag", None)
    if not flag:
        return True
    # FALSE-FLAG = canonical "always blocked" (KITCHEN→STUDIO chimney).
    if flag == "FALSE-FLAG":
        return False
    if context.player.zstate_get(flag):
        return True
    # Object fallback — KITCHEN-WINDOW / TRAP-DOOR `open` property.
    try:
        obj = lookup(flag.lower().replace("-", "_"))
    except NoSuchObjectError:
        return False
    return bool(obj.getp("open", False))


def resolve_dest():
    """
    Pick the destination room — static ``dest`` or routine-driven.

    :returns: The destination Object, or ``None`` when the exit
        routine returns nothing or no destination is configured.
    """
    target = this.getp("dest", None)
    if target is not None:
        return target
    routine_name = this.getp("exit_routine", None)
    if not routine_name:
        return None
    # Generator registers routines snake-cased: TRAP-DOOR-EXIT → trap_door_exit.
    verb_name_snake = routine_name.lower().replace("-", "_")
    zthing_local = _.get_property("thing")
    if zthing_local is None or not zthing_local.has_verb(verb_name_snake):
        return None
    return zthing_local.invoke_verb(verb_name_snake)


if not evaluate_condition():
    print_nogo("condition")
    return

dest = resolve_dest()
if not dest:
    print_nogo("routine")
    return

msg = this.getp("message", None)
if msg:
    print(msg)

veh = _.current_vehicle()
if veh is not None:
    # Gate water-only vehicles when leaving a shore for another land
    # room.  The magic boat's ``vtype="nonlandbit"`` means it floats —
    # the river itself (RIVER-1..5, nonlandbit) → Sandy Beach (a shore
    # exit, non-nonlandbit) is still allowed (the boat drifts to shore),
    # but walking inland from Sandy Beach onto further dry land while
    # still aboard is canonically blocked.  Rule: when BOTH the source
    # and the dest lack ``nonlandbit``, refuse and ask the player to
    # disembark first.
    vtype = veh.getp("vtype", None)
    source = this.getp("source", None)
    if vtype == "nonlandbit" and source is not None and not source.flag("nonlandbit") and not dest.flag("nonlandbit"):
        print("You can't bring the " + veh.desc() + " ashore.  You'll have to disembark first.")
        return
    veh.location = dest
    veh.save()
else:
    context.player.location = dest
    context.player.save()

# Mirror ZIL GOTO's tail — fire enterfunc, then award first-visit discovery via SCORE-OBJ.
# Note: canonical GOTO skips the subsequent M-LOOK when M-ENTER returns truthy,
# but in our translation many M-ENTER handlers return True for state-only reasons
# (Cyclops Room's CYCLOPS-FCN returns True when CYCLOWRATH=0) WITHOUT painting
# the room.  Using ENTERFUNC's return value to gate the look therefore drops
# legitimate room descriptions.  Always fire the post-enter look; handlers that
# already painted (Loud Room's first_look chain) accept the cosmetic double-render
# as the lesser evil vs. dropping descriptions for half the M-ENTER rooms.
if dest.has_verb("enterfunc", recurse=False):
    dest.invoke_verb("enterfunc")
zthing = _.get_property("thing")
if zthing is not None and zthing.has_verb("score_obj"):
    zthing.invoke_verb("score_obj", dest)

if dest.has_verb("look_action"):
    dest.invoke_verb("look_action")
elif dest.has_verb("v_look"):
    # Post-Phase-3 syntax-row refactor: ``look`` resolves to one of the
    # syntax_row dispatchers (look.py, look_at.py, look_in.py, …), all
    # of which read ``context.parser`` — but we're mid-traversal and the
    # parser's command is still the player's typed ``go up`` / ``north``,
    # so a 1-arity ``look <X>`` row would print "Look what?" instead of
    # painting the room.  Call the migrated substrate ``v_look`` directly
    # — it's parser-inert (``--dspec none``) and does the room paint.
    dest.invoke_verb("v_look")
elif dest.has_verb("look"):
    dest.invoke_verb("look")
else:
    # Room doesn't inherit Thing — fall through to the substrate
    # `look` so first-entry prints description + contents.
    zthing = _.get_property("thing")
    if zthing is not None and zthing.has_verb("v_look"):
        zthing.invoke_verb("v_look")
    elif zthing is not None and zthing.has_verb("look"):
        zthing.invoke_verb("look")
    else:
        desc = dest.getp("description", None)
        print(desc if desc else f"You enter {dest.name}.")
