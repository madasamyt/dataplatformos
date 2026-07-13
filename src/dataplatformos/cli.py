"""CLI: pipeline validate|compile|docs|lineage"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dataplatformos import __version__
from dataplatformos.compiler.compile import compile_project
from dataplatformos.compiler.validator import validate_project


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pipeline",
        description="Data Platform OS — design-time pipeline compiler",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="Validate a segment project directory")
    validate.add_argument("project", type=Path)

    compile_cmd = sub.add_parser("compile", help="Compile a segment project to native artifacts")
    compile_cmd.add_argument("project", type=Path)
    compile_cmd.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output directory (default: <project>/dist)",
    )
    compile_cmd.add_argument(
        "--target",
        action="append",
        dest="targets",
        default=None,
        help=(
            "Artifact target (repeatable): airflow, dbt, meltano, debezium, "
            "flink, ml, quality, metrics, products, openlineage, docs, all"
        ),
    )

    docs = sub.add_parser("docs", help="Documentation helpers")
    docs_sub = docs.add_subparsers(dest="docs_command", required=True)
    docs_gen = docs_sub.add_parser("generate", help="Generate lineage docs for a project")
    docs_gen.add_argument("project", type=Path)
    docs_gen.add_argument("-o", "--output", type=Path, default=None)

    lineage = sub.add_parser("lineage", help="Emit OpenLineage JSON for a project")
    lineage.add_argument("project", type=Path)
    lineage.add_argument("-o", "--output", type=Path, default=None)
    lineage.add_argument(
        "--format",
        default="openlineage",
        choices=["openlineage"],
        help="Lineage output format",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "validate":
        result = validate_project(args.project)
        for issue in result.issues:
            stream = sys.stderr if issue.severity == "error" else sys.stdout
            print(issue, file=stream)
        if result.ok:
            print(f"OK: {Path(args.project).resolve()}")
            return 0
        print(
            f"FAILED: {sum(1 for i in result.issues if i.severity == 'error')} error(s)",
            file=sys.stderr,
        )
        return 1

    if args.command == "compile":
        out = args.output or (Path(args.project) / "dist")
        targets = set(args.targets) if args.targets else None
        try:
            result = compile_project(args.project, out, targets=targets)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(f"Compiled {len(result.artifacts)} artifact(s) → {out.resolve()}")
        for art in result.artifacts:
            print(f"  [{art.kind}] {art.relative_path}")
        return 0

    if args.command == "docs" and args.docs_command == "generate":
        out = args.output or (Path(args.project) / "dist")
        try:
            result = compile_project(args.project, out, targets={"docs"})
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(f"Docs → {(out / 'docs' / 'index.md').resolve()}")
        return 0

    if args.command == "lineage":
        out = args.output or (Path(args.project) / "dist")
        try:
            result = compile_project(args.project, out, targets={"openlineage"})
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(f"Lineage → {(out / 'openlineage' / 'lineage.json').resolve()}")
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
