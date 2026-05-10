"""CLI entry point — see :doc:`/reference/zil-importer`."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .converter import extract_all
from .generator import generate_all
from .generator.config import GeneratorIR, GeneratorOptions
from .parser import parse_file


def _expand_manifest(zil_files: list[str]) -> list[str]:
    """
    Recursively resolve ``<INSERT-FILE …>`` directives in ``zil_files``.

    A manifest (e.g. ``zork1.zil``) is a top-level file whose body is
    mostly ``<INSERT-FILE>`` forms; the manifest itself is retained
    because it carries top-level ``<SETG>`` directives that initialise
    zstate slots.

    :param zil_files: One or more ZIL file paths (manifests or sources).
    :returns: Flattened, in-order list of resolved file paths.
    """
    seen: set[str] = set()
    out: list[str] = []

    def visit(zil_path: str) -> None:
        """
        Visit one ZIL file, recursing into ``<INSERT-FILE>`` directives.

        :param zil_path: Path to the ZIL file (resolved before recording).
        """
        zil_path = str(Path(zil_path).resolve())
        if zil_path in seen:
            return
        seen.add(zil_path)
        nodes, _src = parse_file(zil_path)
        base = Path(zil_path).parent
        inserts = [
            str(node[1]) for node in nodes if isinstance(node, list) and len(node) == 2 and node[0] == "INSERT-FILE"
        ]
        # Manifests carry top-level <SETG> forms (e.g. ZORK-NUMBER) — keep them.
        out.append(zil_path)
        for rel in inserts:
            target = base / (rel if rel.endswith(".zil") else rel + ".zil")
            visit(str(target))

    for zil in zil_files:
        visit(zil)
    return out


logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    """
    Run the ZIL importer command-line tool.

    :param argv: CLI arguments (defaults to ``sys.argv[1:]`` when ``None``).
    :returns: Process exit status — ``0`` on success, ``1`` on failure.
    """
    parser = argparse.ArgumentParser(
        description="Convert Infocom ZIL source files to a DjangoMOO bootstrap package.",
    )
    parser.add_argument(
        "zil_files",
        nargs="+",
        metavar="FILE.zil",
        help="One or more ZIL source files to parse (dungeon.zil first, then actions.zil).",
    )
    parser.add_argument(
        "--output",
        default="moo/bootstrap/zork1",
        metavar="DIR",
        help="Output directory for the generated bootstrap package (default: moo/bootstrap/zork1).",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable debug logging.",
    )
    parser.add_argument(
        "--lint",
        action="store_true",
        help=(
            "After generating, run pylint on the output directory and fail "
            "the import if the score drops below --lint-threshold.  "
            "Off by default — pylint takes ~15s on the full Zork 1 bootstrap."
        ),
    )
    parser.add_argument(
        "--lint-threshold",
        type=float,
        default=9.0,
        metavar="SCORE",
        help="Minimum acceptable pylint score (0-10, default 9.0).  Only used with --lint.",
    )
    args = parser.parse_args(argv)

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Flatten <INSERT-FILE> manifests; non-manifest sources pass through unchanged.
    try:
        source_files = _expand_manifest(args.zil_files)
    except (OSError, SyntaxError, ValueError) as exc:
        log.error("Failed to expand manifest: %s", exc)
        return 1
    log.info("Manifest expanded to %d files", len(source_files))

    # Parse all ZIL files and merge their AST nodes
    all_nodes = []
    for path in source_files:
        log.info("Parsing %s ...", path)
        try:
            nodes, _source = parse_file(path)
            all_nodes.extend(nodes)
            log.info("  → %d top-level forms", len(nodes))
        except (OSError, SyntaxError, ValueError) as exc:
            log.error("Failed to parse %s: %s", path, exc)
            return 1

    # Extract IR
    log.info("Extracting world model ...")
    rooms, objects, routines, tables, globals_dict, syntax_dict, synonyms_dict, compound_verb_dict, bare_syntax_dict = (
        extract_all(all_nodes)
    )
    log.info("  Rooms:    %d", len(rooms))
    log.info("  Objects:  %d", len(objects))
    log.info("  Routines: %d", len(routines))
    log.info("  Tables:   %d", len(tables))
    log.info("  Globals:  %d", len(globals_dict))
    log.info("  Syntax:   %d", len(syntax_dict))
    log.info("  Synonyms: %d", len(synonyms_dict))

    if not rooms and not objects:
        log.error("No rooms or objects found — check your input files.")
        return 1

    # Generate bootstrap
    output_dir = Path(args.output)
    log.info("Generating bootstrap at %s ...", output_dir)

    # Per-file pylint adds ~30-60s; raises on the first below-threshold file.
    linter = None
    if args.lint:
        from .lint import Linter  # pylint: disable=import-outside-toplevel

        log.info("Per-file pylint enabled (threshold %.2f)", args.lint_threshold)
        linter = Linter(threshold=args.lint_threshold)

    ir = GeneratorIR(
        tables={name: t.values for name, t in tables.items()},
        globals_dict=globals_dict,
        syntax_dict=syntax_dict,
        synonyms_dict=synonyms_dict,
        compound_verb_dict=compound_verb_dict,
        bare_syntax_dict=bare_syntax_dict,
    )
    options = GeneratorOptions(linter=linter)
    try:
        generate_all(rooms, objects, routines, output_dir, ir=ir, options=options)
    except RuntimeError as exc:
        log.error("%s", exc)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
