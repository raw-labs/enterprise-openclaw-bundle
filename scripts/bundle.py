#!/usr/bin/env python3
"""Build/release owner CLI; does not deploy infrastructure or Agents."""

import argparse
import gzip
import io
import json
import posixpath
import re
import subprocess
import sys
import tarfile
from pathlib import Path

from common import (
    digest,
    load,
    read_release,
    release_file,
    require,
    run,
    safe_path,
)

ROOT = Path(__file__).resolve().parents[1]


def source_files(release, selection):
    path = safe_path(Path(selection).parent, release["sources"]["oce"]["files"])
    require(
        digest(path.read_bytes()) == release["sources"]["oce"]["filesSha256"],
        "source inventory checksum mismatch",
    )
    return load(path)


def verify_source(release, selection, source):
    expected = source_files(release, selection)
    # No untracked build-context content or symlinks. Export only Git files.
    actual = {}
    for path in Path(source).rglob("*"):
        require(not path.is_symlink(), "source export must not contain symlinks")
        if path.is_file():
            actual[str(path.relative_to(source))] = digest(path.read_bytes())
    require(actual == expected, "source export differs from pinned inventory")
    chart = Path(source) / release["chart"]["path"]
    require(
        f"version: {release['chart']['version']}\n"
        in (chart / "Chart.yaml").read_text(),
        "chart version/source mismatch",
    )
    recipe = (Path(source) / release["build"]["runtime"]["dockerfile"]).read_text()
    require(
        release["sources"]["openclaw"]["commit"] in recipe
        and release["sources"]["openclaw"]["archiveSha256"] in recipe,
        "runtime Dockerfile/source selection mismatch",
    )
    runtime = release["runtime"]
    require(
        digest((Path(source) / runtime["inventoryHelper"]).read_bytes())
        == runtime["inventoryHelperSha256"],
        "inventory helper mismatch",
    )
    if release["schemaVersion"] == 2:
        require(
            "ENV OPENAI_CODEX_VERSION=" + runtime["codexVersion"] in recipe,
            "stock Codex/source mismatch",
        )
        for name, expected in runtime["bridgePatches"].items():
            require(
                digest(safe_path(source, name).read_bytes()) == expected
                and expected in recipe,
                "bridge patch mismatch",
            )
        lock = (Path(source) / "pnpm-lock.yaml").read_text()
        for name, dependency in release["rendererDependencies"].items():
            require(
                re.search(
                    re.escape(name + "@" + dependency["version"])
                    + r":\n    resolution: \{integrity: "
                    + re.escape(dependency["integrity"])
                    + r"\}",
                    lock,
                ),
                "renderer dependency differs from selected source lockfile",
            )


def deterministic_tar(files, prefix=""):
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.GNU_FORMAT) as tar:
        for name, (data, mode) in sorted(files.items()):
            info = tarfile.TarInfo(prefix + name)
            info.size = len(data)
            info.mode = mode
            info.mtime = 0
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            tar.addfile(info, io.BytesIO(data))
    out = io.BytesIO()
    with gzip.GzipFile(
        fileobj=out, mode="wb", filename="", mtime=0, compresslevel=9
    ) as gz:
        gz.write(raw.getvalue())
    return out.getvalue()


def package(args, release):
    source = Path(args.source).resolve()
    verify_source(release, args.release, source)
    dest = Path(args.output).resolve()
    require(not dest.exists(), "artifact output already exists")
    chart = source / release["chart"]["path"]
    run(
        ["helm", "lint", chart, "-f", ROOT / "defaults/lint-values.json"],
        stdout=subprocess.PIPE,
    )
    files = {}
    if release["schemaVersion"] == 2:
        from stock import renderer_files

        files.update(renderer_files(release, Path(args.dependencies)))
    chart_files = {
        str(p.relative_to(chart)): (p.read_bytes(), 0o644)
        for p in sorted(chart.rglob("*"))
        if p.is_file()
    }
    chart_files["LICENSE"] = ((source / "LICENSE").read_bytes(), 0o644)
    chart_data = deterministic_tar(chart_files, release["chart"]["name"] + "/")
    chart_name = (
        "chart/" + release["chart"]["name"] + "-" + release["chart"]["version"] + ".tgz"
    )
    files[chart_name] = (chart_data, 0o644)
    shipped = [
        "scripts/render-installation-profile.mjs",
        "scripts/prepare-bootstrap-volume",
        "deploy/profiles/openclaw.json",
        "deploy/profiles/codex.json",
        "docs/guides/repository-credentials/installation.md",
    ]
    for name in shipped:
        data = (source / name).read_bytes()
        if name.endswith(".md"):
            # Keep upstream prose and commands, resolve relative references to the exact source.
            base = (
                release["sources"]["oce"]["repository"].removesuffix(".git")
                + "/blob/"
                + release["sources"]["oce"]["commit"]
                + "/"
            )

            def absolute_link(match, base=base, name=name):
                target = match.group(1)
                if "://" in target or target.startswith("#"):
                    return match.group(0)
                return (
                    "]("
                    + base
                    + posixpath.normpath(
                        posixpath.join(posixpath.dirname(name), target)
                    )
                    + ")"
                )

            data = re.sub(r"\]\(([^)]+)\)", absolute_link, data.decode()).encode()
        files["upstream/" + name] = (
            data,
            0o755 if name.startswith("scripts/") else 0o644,
        )
    # Explicit profile configuration overlay; renderer and chart remain unchanged.
    if "defaults/codex-profile.json" in release["payloadFiles"]:
        files["upstream/deploy/profiles/codex.json"] = (
            release_file(
                args.release, ROOT, "defaults/codex-profile.json"
            ).read_bytes(),
            0o644,
        )
    files["notices/OCE-LICENSE"] = ((source / "LICENSE").read_bytes(), 0o644)
    for name in ["THIRD_PARTY_NOTICES.md"]:
        if (source / name).exists():
            files["notices/OCE-" + name] = ((source / name).read_bytes(), 0o644)
    for name in ["common.py", "install.py"]:
        files["scripts/" + name] = ((ROOT / "scripts" / name).read_bytes(), 0o755)
    for name in release["payloadFiles"]:
        payload = release_file(args.release, ROOT, name)
        files[name] = (payload.read_bytes(), 0o644)
    files["INSTALL.md"] = ((ROOT / "docs/install.md").read_bytes(), 0o644)
    files["OPERATE.md"] = ((ROOT / "docs/operate.md").read_bytes(), 0o644)
    # Runtime build overlay/private build inputs are deliberately excluded.
    copy = json.loads(json.dumps(release))
    copy["chart"]["artifact"] = chart_name
    copy["chart"]["sha256"] = digest(chart_data)
    files["release.json"] = (
        (json.dumps(copy, indent=2, sort_keys=True) + "\n").encode(),
        0o644,
    )
    q = release["qualification"]
    for receipt in q.get("nativeReceipts", {}).values():
        files[receipt["path"]] = (
            safe_path(Path(args.release).parent, receipt["path"]).read_bytes(),
            0o644,
        )
    if q["status"] == "qualified":
        files[q["receipt"]] = (
            safe_path(Path(args.release).parent, q["receipt"]).read_bytes(),
            0o644,
        )
    manifest = {name: digest(data) for name, (data, _) in files.items()}
    files["manifest.json"] = (
        (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode(),
        0o644,
    )
    artifact = deterministic_tar(files, release["id"] + "/")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(artifact)
    checksum = dest.with_name(dest.name + ".sha256")
    checksum.write_text(digest(artifact) + "  " + dest.name + "\n")
    print(
        f"Bundle: {dest}\nSHA256: {digest(artifact)}\nStatus: {q['status']}; no images embedded"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate")
    p = sub.add_parser("package")
    p.add_argument("--source", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--dependencies", required=True)
    args = parser.parse_args()
    release = read_release(args.release, ROOT)
    if args.command == "validate":
        source_files(release, args.release)
    else:
        package(args, release)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as error:
        print(f"bundle: {error}", file=sys.stderr)
        sys.exit(1)
