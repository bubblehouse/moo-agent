#!moo verb null_f --on "Thing" --dspec this
# pylint: disable=return-outside-function,undefined-variable,no-name-in-module
"""
Stub for ZIL's NULL-F no-op routine.

Zork's ZIL defines ``<ROUTINE NULL-F (...) <>>`` so the translator emits
its own null_f.py for that game. HHG's ZIL omits NULL-F entirely, but
substrate-generated code (PRE-TAKE, PRE-BOARD, describe_object,
look_inside, …) still calls ``_.thing.null_f()``. Without this
stub HHG raises ``AttributeError: ... no attribute 'null_f'`` on those
paths.

Idempotent for Zork: the static copy and Zork's translator output have
identical bodies (return False), and the generator skips translator
emits that collide with static templates — so this doesn't double-
register the verb.
"""

return False
