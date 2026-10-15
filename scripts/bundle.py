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
HANDOFF_DOCUMENTS = {
    "AGENTS.md": ROOT / "delivery/AGENTS.md",
    "INSTALL.md": ROOT / "docs/install.md",
    "UPDATE.md": ROOT / "docs/update.md",
    "OPERATE.md": ROOT / "docs/operate.md",
}


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
    for preset in release.get("presets", []):
        require(expected.get(preset["path"].removeprefix("/app/")) == preset["sha256"], "preset/source inventory mismatch")
    for plugin in release.get("pluginPackages", []):
        for name, checksum in plugin["files"].items():
            path = "deploy/bundle/plugins/" + plugin["id"] + "/" + name
            require(expected.get(path) == checksum, "plugin/source inventory mismatch")
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
            re.search(r"^ENV OPENAI_CODEX_VERSION=" + re.escape(runtime["codexVersion"]) + r"$", recipe, re.MULTILINE),
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


def cli_files(directory, release):
    directory = Path(directory)
    cli = load(directory / "cli.json")
    require(
        cli["oceCommit"] == release["sources"]["oce"]["commit"]
        and cli["sourceInventorySha256"] == release["sources"]["oce"]["filesSha256"],
        "CLI belongs to another resolved source",
    )
    require(
        release.get("operatorCli", cli) == cli, "CLI differs from release provenance"
    )
    require(
        set(cli["binaries"])
        == {
            f"occ-{os_name}-{arch}"
            for os_name in ("darwin", "linux")
            for arch in ("amd64", "arm64")
        },
        "all operator CLI binaries required",
    )
    require(
        cli["tests"]["pass"] > 0 and cli["tests"]["fail"] == cli["tests"]["skip"] == 0,
        "CLI tests must pass without skips",
    )
    files = {}
    for name, info in cli["binaries"].items():
        binary = directory / name
        require(not binary.is_symlink(), "CLI binary links rejected")
        require(
            name == f"occ-{info['os']}-{info['architecture']}"
            and digest(binary.read_bytes()) == info["sha256"],
            "CLI binary changed after verification",
        )
        files["lib/occ/" + name] = (binary.read_bytes(), 0o755)
    return cli, files


def package(args, release):
    source = Path(args.source).resolve()
    verify_source(release, args.release, source)
    dest = Path(args.output).resolve()
    require(not dest.exists(), "artifact output already exists")
    chart = source / release["chart"]["path"]
    lint_values = ROOT / "tests/fixtures/helm-lint-values.json"
    # Unbuilt packaging tests use the fixture; real releases lint their selected image.
    controller = (
        release["images"]["controller"]["reference"]
        or load(lint_values)["images"]["controller"]
    )
    run(
        [
            "helm",
            "lint",
            chart,
            "-f",
            lint_values,
            "--set-string",
            "images.controller=" + controller,
        ],
        stdout=subprocess.PIPE,
    )
    cli, files = cli_files(Path(args.dependencies).parent / "cli", release)
    files["bin/occ"] = ((ROOT / "delivery/occ").read_bytes(), 0o755)
    files["bin/prepare"] = ((ROOT / "delivery/prepare").read_bytes(), 0o755)
    if release["schemaVersion"] == 2:
        from stock import renderer_files

        files.update(renderer_files(release, Path(args.dependencies)))
    chart_files = {
        str(p.relative_to(chart)): (p.read_bytes(), 0o644)
        for p in sorted(chart.rglob("*"))
        if p.is_file()
    }
    chart_files["LICENSE"] = ((source / "LICENSE").read_bytes(), 0o644)
    # Keep OCE's paths: its renderer, origin helper and upgrade tool use this chart.
    chart_name = "oce/" + release["chart"]["path"]
    for name, content in chart_files.items():
        files[chart_name + "/" + name] = content
    shipped = [
        "scripts/render-installation-profile.mjs",
        "scripts/render-repository-credentials-origin.mjs",
        "scripts/prepare-bootstrap-volume",
        "deploy/profiles/openclaw.json",
        "deploy/profiles/codex.json",
        "docs/guides/deploy/installation-profiles.md",
        "docs/guides/deploy/production-installation.md",
        "docs/guides/deploy/production-agents.md",
        "docs/guides/deploy/production-upgrade.md",
        "docs/guides/deploy/production-upgrade-recovery.md",
        "docs/guides/deploy/upgrade-baseline.md",
        "docs/guides/deploy/upgrade-checklist.md",
        "docs/flows/coordinated-production-upgrade.md",
        "docs/guides/repository-credentials/installation.md",
    ]
    for preset in release.get("presets", []):
        shipped.append(preset["path"].removeprefix("/app/"))
    shipped.extend(
        str(p.relative_to(source))
        for p in sorted((source / "scripts").glob("upgrade-*"))
        if p.is_file()
    )
    shipped.extend(
        name
        for name in (
            "scripts/split-layout-adopt.mjs",
            "scripts/split-layout-tenants.mjs",
            "apps/controller/src/drivers/compute/kubernetes/resource-name.ts",
            "apps/controller/src/drivers/openai-endpoint.ts",
            "packages/occ/src/image-reference.ts",
            "packages/contracts/src/api/plain-text.ts",
        )
        if (source / name).is_file()
    )
    for directory in ("deploy/examples/production", "deploy/logging"):
        shipped.extend(
            str(p.relative_to(source))
            for p in sorted((source / directory).rglob("*"))
            if p.is_file()
        )
    # Follow operator guides and product reference, excluding development manuals.
    pending = [name for name in shipped if name.endswith(".md")]
    while pending:
        name = pending.pop()
        for target in re.findall(r"\]\(([^)]+)\)", (source / name).read_text()):
            if "://" in target or target.startswith("#"):
                continue
            relative = posixpath.normpath(
                posixpath.join(posixpath.dirname(name), target.split("#")[0])
            )
            if (
                relative.startswith(("docs/guides/", "docs/reference/"))
                and relative != "docs/reference/README.md"
                and relative.endswith(".md")
                and relative not in shipped
                and (source / relative).is_file()
            ):
                shipped.append(relative)
                pending.append(relative)
    for name in shipped:
        data = (source / name).read_bytes()
        files["oce/" + name] = (
            data,
            0o755 if name.startswith("scripts/") else 0o644,
        )
    # Local links use the delivered kit; additional reference links pin the source.
    source_url = (
        release["sources"]["oce"]["repository"].removesuffix(".git")
        + "/blob/"
        + release["sources"]["oce"]["commit"]
        + "/"
    )
    for name in shipped:
        if name.endswith(".md"):

            def link(match, name=name):
                target = match.group(1)
                if "://" in target or target.startswith("#"):
                    return match.group(0)
                path = posixpath.normpath(
                    posixpath.join(posixpath.dirname(name), target.split("#")[0])
                )
                return (
                    match.group(0)
                    if "oce/" + path in files
                    else "]("
                    + source_url
                    + posixpath.normpath(
                        posixpath.join(posixpath.dirname(name), target)
                    )
                    + ")"
                )

            data, mode = files["oce/" + name]
            files["oce/" + name] = (
                re.sub(r"\]\(([^)]+)\)", link, data.decode()).encode(),
                mode,
            )
    files["notices/OCE-LICENSE"] = ((source / "LICENSE").read_bytes(), 0o644)
    for name in ["THIRD_PARTY_NOTICES.md"]:
        if (source / name).exists():
            files["notices/OCE-" + name] = ((source / name).read_bytes(), 0o644)
    for name in ("integrity.py", "prepare.py"):
        files["lib/" + name] = ((ROOT / "delivery" / name).read_bytes(), 0o644)
    for name in release["payloadFiles"]:
        payload = release_file(args.release, ROOT, name)
        files[name] = (payload.read_bytes(), 0o644)
    for name, document in HANDOFF_DOCUMENTS.items():
        files[name] = (document.read_bytes(), 0o644)
    # Runtime build inputs are deliberately excluded.
    copy = json.loads(json.dumps(release))
    copy["operatorCli"] = cli
    copy["chart"]["artifact"] = chart_name
    copy["profiles"] = {
        "openclaw": "oce/deploy/profiles/openclaw.json",
        "codex": "defaults/codex-profile.json",
    }
    copy["upstreamGuides"] = {
        name: release["sources"]["oce"]["repository"].removesuffix(".git")
        + "/blob/"
        + release["sources"]["oce"]["commit"]
        + "/"
        + name
        for name in shipped
        if name.endswith(".md")
    }
    q = release["qualification"]
    copy["qualification"]["nativeReceipts"] = {
        arch: {
            "url": "https://github.com/raw-labs/enterprise-openclaw-bundle/releases/download/"
            + release["id"]
            + "/"
            + receipt["path"],
            "sha256": receipt["sha256"],
        }
        for arch, receipt in q.get("nativeReceipts", {}).items()
    }
    files["metadata/release.json"] = (
        (json.dumps(copy, indent=2, sort_keys=True) + "\n").encode(),
        0o644,
    )
    manifest = {name: digest(data) for name, (data, _) in files.items()}
    files["metadata/manifest.json"] = (
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
