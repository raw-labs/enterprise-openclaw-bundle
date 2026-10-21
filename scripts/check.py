#!/usr/bin/env python3
"""Run offline contributor checks, optionally followed by prepared-source integration tests."""

import argparse
import ast
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(command, **kwargs):
    subprocess.run([str(part) for part in command], cwd=ROOT, check=True, **kwargs)


def repository_links():
    documents = [
        *sorted(ROOT.glob("*.md")),
        *sorted((ROOT / "docs").glob("*.md")),
    ]
    for document in documents:
        for target in re.findall(r"\]\(([^)]+)\)", document.read_text()):
            path = target.split("#", 1)[0]
            if path and "://" not in path and not (document.parent / path).exists():
                raise ValueError(
                    f"broken repository link: {document.relative_to(ROOT)}: {target}"
                )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--integration",
        action="store_true",
        help="also require and test resolved source, dependencies and CLI binaries",
    )
    parser.add_argument(
        "--selection", type=Path, default=ROOT / ".work/resolved/candidate.json"
    )
    args = parser.parse_args()
    if args.integration:
        selection = args.selection.resolve()
        missing = [
            path
            for path in (
                selection,
                selection.parent / "source",
                selection.parent / "dependencies",
                selection.parent / "cli/cli.json",
            )
            if not path.exists()
        ]
        if missing:
            raise ValueError(
                "integration inputs missing; follow CONTRIBUTING.md: "
                + ", ".join(str(path) for path in missing)
            )
    run([sys.executable, ROOT / "scripts/release.py", "validate-definitions"])
    for directory in ("scripts", "delivery", "tests"):
        for path in (ROOT / directory).rglob("*.py"):
            ast.parse(path.read_text(), filename=str(path))
    for name in ("delivery/occ", "delivery/prepare"):
        ast.parse((ROOT / name).read_text(), filename=name)
    for path in [
        *sorted((ROOT / "scripts").glob("*.mjs")),
        *sorted((ROOT / "tests").glob("*.mjs")),
    ]:
        run(["node", "--check", path])
    run(["bash", "-n", ROOT / "scripts/setup-docker.sh"])
    repository_links()
    run([sys.executable, "-m", "unittest", "discover", "-s", "tests/unit", "-v"])
    if args.integration:
        run(
            [
                sys.executable,
                "-m",
                "unittest",
                "discover",
                "-s",
                "tests/integration",
                "-v",
            ],
            env=dict(os.environ, BUNDLE_TEST_SELECTION=str(selection)),
        )
    print(
        "Contributor checks passed"
        + (
            "; packaging integration passed"
            if args.integration
            else "; integration and native qualification were not requested"
        )
    )


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        sys.exit(f"check: {error}")
