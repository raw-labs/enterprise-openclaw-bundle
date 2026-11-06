"""Verify an extracted bundle before OCE's upgrade helper uses its chart."""

import hashlib
import os
import sys
from pathlib import Path

from integrity import load, require, verify_package


def verify_upgrade_source(root, revision, outputs):
    root = Path(root).resolve()
    require(Path.cwd().resolve() == root / "oce", "run from the candidate oce directory")
    verify_package(root)
    release = load(root / "metadata/release.json")
    require(release["sources"]["oce"]["commit"] == revision, "package/source revision mismatch")
    chart = Path("deploy/helm/openclaw-enterprise")
    require((chart / "Chart.yaml").is_file(), "missing packaged chart")
    directories = {chart.resolve(), *(p.resolve() for p in chart.rglob("*") if p.is_dir())}
    identities = {(p.stat().st_dev, p.stat().st_ino) for p in directories}
    for output in outputs:
        path = Path(output).resolve()
        for ancestor in (path, *path.parents):
            if ancestor.exists():
                info = ancestor.stat()
                require((info.st_dev, info.st_ino) not in identities,
                        "keep evidence and baseline files outside the packaged Helm chart")
    digest = hashlib.sha256()

    def visit(directory):
        entries = sorted(directory.iterdir())
        for path in entries:
            if path.is_file():
                digest.update(os.fsencode(path) + b"\0" + path.read_bytes() + b"\0")
        for path in entries:
            if path.is_dir():
                visit(path)

    visit(chart)
    return digest.hexdigest()


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    try:
        print(verify_upgrade_source(Path(__file__).resolve().parents[1], sys.argv[1], sys.argv[2:]))
    except (ValueError, OSError, KeyError) as error:
        sys.exit(f"packaged upgrade source: {error}")
