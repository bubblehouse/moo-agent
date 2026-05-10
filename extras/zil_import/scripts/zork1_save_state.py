"""Snapshot the current zork1 world state to JSON.

Replaces the moo-core ``moo_save_state`` management command (reverted under
Rule Zero — Zork-specific snapshotting belongs here, not in
``moo/core/management/commands/``).

Walks every descendant of ``Zork Root`` (rooms, things, actors, exits) plus
the System Object's ``zstate_*`` properties on the Wizard, and emits the
result as a JSON document on stdout (or to ``--output PATH``).  The output
is human-readable for archival / debugging — it is NOT a load-back format.
A future ``zork1_load_state.py`` could consume it, but bootstrap re-init is
fast enough that nobody has needed one.

Usage::

    uv run python -m extras.zil_import.scripts.zork1_save_state
    uv run python -m extras.zil_import.scripts.zork1_save_state --output snap.json
    uv run python -m extras.zil_import.scripts.zork1_save_state --hostname zork1.local
"""

import argparse
import subprocess
import sys
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _THIS_DIR.parents[3]


_SNAPSHOT_SNIPPET = r"""
import json
from django.contrib.sites.models import Site
from moo.core.code import ContextManager
from moo.core.models.object import Object

site = Site.objects.get(domain={hostname!r})
ContextManager.set_site(site)
zr = Object.global_objects.filter(name="Zork Root", site=site).first()
wiz = Object.global_objects.filter(name="Wizard", site=site).first()

out = {{"hostname": {hostname!r}, "objects": [], "zstate": {{}}}}

if zr is not None:
    visited = set()
    stack = [zr]
    while stack:
        obj = stack.pop()
        if obj.pk in visited:
            continue
        visited.add(obj.pk)
        rec = {{
            "pk": obj.pk,
            "name": obj.name,
            "location": obj.location.name if obj.location else None,
            "obvious": bool(obj.obvious),
            "aliases": list(obj.aliases.values_list("alias", flat=True)),
            "properties": {{}},
        }}
        for prop in obj.properties.all():
            try:
                rec["properties"][prop.name] = obj.get_property(prop.name)
            except Exception:
                rec["properties"][prop.name] = "<unreadable>"
        out["objects"].append(rec)
        for child in obj.children.all():
            stack.append(child)

if wiz is not None:
    for prop in wiz.properties.filter(name__startswith="zstate_"):
        try:
            out["zstate"][prop.name] = wiz.get_property(prop.name)
        except Exception:
            out["zstate"][prop.name] = "<unreadable>"

print(json.dumps(out, indent=2, default=str))
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Snapshot zork1 world state.")
    parser.add_argument(
        "--hostname",
        default="zork1.local",
        help="Site domain to snapshot (default: zork1.local).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Write JSON to PATH instead of stdout.",
    )
    parser.add_argument(
        "--container",
        default="django-moo-shell-1",
        help="Docker container name running the Django shell.",
    )
    args = parser.parse_args()

    snippet = _SNAPSHOT_SNIPPET.format(hostname=args.hostname)
    result = subprocess.run(
        ["docker", "exec", args.container, "/usr/app/bin/python", "/usr/app/src/manage.py", "shell", "-c", snippet],
        cwd=_REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"snapshot failed: {result.stderr}", file=sys.stderr)
        return result.returncode

    payload = result.stdout
    if args.output is not None:
        args.output.write_text(payload, encoding="utf-8")
        print(f"wrote {args.output} ({len(payload)} bytes)", file=sys.stderr)
    else:
        sys.stdout.write(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
