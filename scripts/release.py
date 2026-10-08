#!/usr/bin/env python3
"""Resolve one bundle definition; finish the private release after native checks."""

import argparse
import base64
import hashlib
import io
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path
from types import SimpleNamespace

from bundle import package, verify_source
from common import (
    HASH,
    IMAGE,
    ROLES,
    SHA,
    digest,
    load,
    read_release,
    require,
    run,
    safe_path,
    save,
)
from stock import github_json

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "raw-labs/enterprise-openclaw-bundle"
SEMVER = re.compile(
    r"v(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)-(alpha|beta|rc)\.[1-9]\d*"
)


def pinned_file(reference):
    require(set(reference) == {"path", "sha256"}, "file requires path and sha256")
    require(HASH.fullmatch(reference["sha256"]), "invalid ingredient checksum")
    path = safe_path(ROOT, reference["path"])
    require(
        path.is_file() and digest(path.read_bytes()) == reference["sha256"],
        f"ingredient changed: {reference['path']}",
    )
    return path


def definition(path):
    path = Path(path).resolve()
    require(
        path.is_relative_to(ROOT / "bundles") and path.name == "bundle.json",
        "select bundles/<version>/bundle.json",
    )
    spec = load(path)
    require(
        set(spec)
        == {
            "schemaVersion",
            "version",
            "oce",
            "openclawCommit",
            "codexVersion",
            "architectures",
            "recipe",
            "presets",
            "plugins",
            "codexProfile",
            "installationExample",
        },
        "unknown or missing bundle fields",
    )
    require(
        spec["schemaVersion"] == 1 and SEMVER.fullmatch(spec["version"]),
        "use an immutable numbered alpha, beta or rc version",
    )
    require(path.parent.name == spec["version"], "folder/version mismatch")
    require(
        set(spec["oce"]) == {"repository", "commit"}
        and re.fullmatch(
            r"https://github.com/[\w.-]+/[\w.-]+\.git", spec["oce"]["repository"]
        )
        and SHA.fullmatch(spec["oce"]["commit"]),
        "OCE requires an exact GitHub commit",
    )
    require(SHA.fullmatch(spec["openclawCommit"]), "OpenClaw requires an exact commit")
    require(
        re.fullmatch(r"\d+\.\d+\.\d+", spec["codexVersion"]), "invalid Codex version"
    )
    require(
        spec["architectures"] == ["linux/amd64", "linux/arm64"],
        "both native targets required",
    )
    require(isinstance(spec["presets"], list), "presets must be a list")
    require(
        isinstance(spec["plugins"], list)
        and spec["plugins"]
        and len(set(spec["plugins"])) == len(spec["plugins"])
        and all(re.fullmatch(r"[a-z][a-z0-9-]*", p) for p in spec["plugins"]),
        "select unique bundled plugin IDs",
    )
    recipe = load(pinned_file(spec["recipe"]))
    require(
        set(recipe) == {"type", "noticeLayer", "patches", "confinement"}
        and recipe["type"] == "oce-stock",
        "unsupported recipe",
    )
    pinned_file(recipe["noticeLayer"])
    require(isinstance(recipe["patches"], list), "patches must be a list")
    for patch in recipe["patches"]:
        pinned_file(patch)
    require(
        set(recipe["confinement"])
        == {
            "scripts/lib/codex-seccomp-profile.mjs",
            ".github/actions/run-ci-lane/codex-sandbox.apparmor",
        }
        and all(HASH.fullmatch(h) for h in recipe["confinement"].values()),
        "pin reviewed source confinement inputs in the recipe",
    )
    targets = set()
    for ref in spec["presets"]:
        source = pinned_file(ref)
        require(source.name.endswith("-preset.json"), "preset must be a JSON template")
        preset = load(source)
        require(
            preset.get("template", {}).get("agent", {}).get("plugins", {}) == {},
            "Connections and live Agent plugin configuration are outside this milestone",
        )
        require(source.name not in targets, "duplicate preset filename")
        targets.add(source.name)
    for key in ("codexProfile", "installationExample"):
        pinned_file(spec[key])
    return spec, recipe


def export_source(spec, output, from_git=None):
    src = spec["oce"]
    with tempfile.TemporaryDirectory() as temporary:
        repo = Path(from_git).resolve() if from_git else Path(temporary) / "git"
        if from_git:
            remotes = subprocess.check_output(
                ["git", "-C", str(repo), "remote", "-v"], text=True
            )
            require(src["repository"] in remotes, "source repository remote mismatch")
        else:
            run(["git", "init", "-q", repo])
            run(
                [
                    "git",
                    "-C",
                    repo,
                    "fetch",
                    "--depth=1",
                    src["repository"],
                    src["commit"],
                ]
            )
        commit = subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", src["commit"] + "^{commit}"],
            text=True,
        ).strip()
        require(commit == src["commit"], "exported source commit mismatch")
        epoch = int(
            subprocess.check_output(
                ["git", "-C", str(repo), "show", "-s", "--format=%ct", commit]
            )
        )
        archive = subprocess.check_output(
            ["git", "-C", str(repo), "archive", "--format=tar", commit]
        )
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            require(
                all(m.isfile() or m.isdir() for m in tar.getmembers()),
                "source links/devices rejected",
            )
            for member in tar.getmembers():
                safe_path(output, member.name)
            output.mkdir(parents=True)
            tar.extractall(output, filter="data")
    return {**src, "archiveSha256": digest(archive), "commitEpoch": epoch}


def resolve(args):
    spec, recipe = definition(args.definition)
    out = Path(args.output).resolve()
    require(not out.exists(), "resolved output already exists")
    out.mkdir(parents=True)
    source = out / "source"
    oce = export_source(spec, source, args.from_git)
    original_license = (source / "LICENSE").read_bytes()
    for patch in recipe["patches"]:
        # Apply only tracked, hash-checked source patches. Git rejects paths outside this export.
        env = dict(os.environ, GIT_CEILING_DIRECTORIES=str(source.parent))
        run(["git", "apply", "--check", pinned_file(patch)], cwd=source, env=env)
        run(["git", "apply", pinned_file(patch)], cwd=source, env=env)
    require(
        (source / "LICENSE").read_bytes() == original_license,
        "upstream license must be preserved",
    )
    for path, expected in recipe["confinement"].items():
        require(
            digest(safe_path(source, path).read_bytes()) == expected,
            "confinement input changed; review and repin recipe",
        )
    files = {}
    for path in sorted(source.rglob("*")):
        require(not path.is_symlink(), "source symlink rejected")
        if path.is_file():
            files[str(path.relative_to(source))] = digest(path.read_bytes())
    save(out / "source-files.json", files)
    oce.update(
        files="source-files.json",
        filesSha256=digest((out / "source-files.json").read_bytes()),
    )
    dockerfile = (source / "deploy/runtime/Dockerfile").read_text()

    def one(pattern, text=dockerfile):
        matches = re.findall(pattern, text, re.MULTILINE)
        require(len(matches) == 1, f"unsupported source recipe: {pattern}")
        return matches[0]

    oc = one(r"^ARG OPENCLAW_COMMIT=([a-f0-9]{40})$")
    codex = one(r"^ENV OPENAI_CODEX_VERSION=(\d+\.\d+\.\d+)$")
    require(
        oc == spec["openclawCommit"] and codex == spec["codexVersion"],
        "bundle/runtime source mismatch",
    )
    selected_plugins = one(
        r"OPENCLAW_INTERNAL_DOCKER_BUILD_PLUGIN_IDS=([a-z0-9,-]+)"
    ).split(",")
    retained_plugins = one(r"OPENCLAW_EXTENSIONS=([a-z0-9,-]+)").split(",")
    require(
        spec["plugins"] == selected_plugins == retained_plugins,
        "plugin selection differs from runtime recipe; select a compatible fork or patch",
    )
    oc_archive = one(r"echo '([a-f0-9]{64})  /tmp/openclaw-source.tar.gz'")
    build = {
        key: one(r"^ARG " + arg + r"=([^\s]+)$")
        for key, arg in (
            ("nodeBaseImage", "NODE_BASE_IMAGE"),
            ("nodeRuntimeBaseImage", "NODE_RUNTIME_BASE_IMAGE"),
        )
    }
    require(
        all(IMAGE.fullmatch(ref) for ref in build.values()),
        "source base images must be digest pinned",
    )
    build.update(
        controller={"dockerfile": "Dockerfile", "target": "runtime"},
        runtime={"dockerfile": "deploy/runtime/Dockerfile", "target": "runtime"},
        repositoryCredentials={
            "dockerfile": "deploy/runtime/Dockerfile",
            "target": "repository-credentials-service",
        },
        noticeLayer={
            "fragment": "recipe/notices.fragment",
            "sha256": recipe["noticeLayer"]["sha256"],
        },
    )
    patches = {
        p: h
        for p, h in files.items()
        if p.startswith("deploy/runtime/") and p.endswith(".patch") and h in dockerfile
    }
    chart_path = "deploy/helm/openclaw-enterprise"
    chart_version = one(
        r"^version: ([\w.+-]+)$", (source / chart_path / "Chart.yaml").read_text()
    )
    payload = {"defaults/" + Path(ref["path"]).name: ref for ref in spec["presets"]}
    payload["defaults/codex-profile.json"] = spec["codexProfile"]
    payload["profiles/aws-example.json"] = spec["installationExample"]
    for name, ref in payload.items():
        target = safe_path(out, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(pinned_file(ref), target)
    (out / "recipe").mkdir()
    shutil.copyfile(pinned_file(recipe["noticeLayer"]), out / "recipe/notices.fragment")
    shutil.copyfile(args.definition, out / "bundle.json")
    lock = (source / "pnpm-lock.yaml").read_text()
    tldts = load(source / "apps/controller/package.json")["dependencies"]["tldts"]
    core = one(
        r"  tldts@"
        + re.escape(tldts)
        + r":\n    dependencies:\n      tldts-core: ([\d.]+)",
        lock,
    )
    dependencies = {}
    cache = Path(args.dependency_cache) if args.dependency_cache else None
    (out / "dependencies").mkdir()
    for name, version in (("tldts", tldts), ("tldts-core", core)):
        integrity = one(
            r"  "
            + re.escape(name + "@" + version)
            + r":\n    resolution: \{integrity: ([^}]+)\}",
            lock,
        )
        filename = f"{name}-{version}.tgz"
        if cache and (cache / filename).is_file():
            data = (cache / filename).read_bytes()
        else:
            with urllib.request.urlopen(
                f"https://registry.npmjs.org/{name}/-/{filename}", timeout=120
            ) as response:
                data = response.read()
        actual = "sha512-" + base64.b64encode(hashlib.sha512(data).digest()).decode()
        require(
            actual == integrity,
            "renderer tarball differs from selected source lockfile",
        )
        (out / "dependencies" / filename).write_bytes(data)
        dependencies[name] = {
            "version": version,
            "integrity": integrity,
            "archiveSha256": digest(data),
        }
    images = {
        role: {"reference": None, "platforms": {}, "oceCommit": oce["commit"]}
        for role in ROLES
    }
    images["runtime"].update(openclawCommit=oc, codexVersion=codex)
    selection = {
        "schemaVersion": 2,
        "id": spec["version"],
        "kind": "candidate",
        "architectures": spec["architectures"],
        "definitionSha256": digest(Path(args.definition).read_bytes()),
        "recipe": spec["recipe"],
        "modifications": recipe["patches"],
        "plugins": spec["plugins"],
        "sources": {
            "oce": oce,
            "openclaw": {
                "repository": "https://github.com/openclaw/openclaw.git",
                "commit": oc,
                "archiveSha256": oc_archive,
            },
        },
        "chart": {
            "name": "openclaw-enterprise",
            "path": chart_path,
            "sourceCommit": oce["commit"],
            "version": chart_version,
        },
        "runtime": {
            "selection": "upstream-stock",
            "overlay": None,
            "codexVersion": codex,
            "inventoryHelper": "scripts/build-runtime-assets.mjs",
            "inventoryHelperSha256": files["scripts/build-runtime-assets.mjs"],
            "bridgePatches": patches,
        },
        "build": build,
        "rendererDependencies": dependencies,
        "images": images,
        "seccomp": {"profiles": {}},
        "payloadFiles": {name: ref["sha256"] for name, ref in payload.items()},
        "distribution": {
            "registry": "ghcr.io",
            "namespace": REPOSITORY,
            "visibility": "private",
            "productVersion": spec["version"],
        },
        "qualification": {"status": "unqualified", "customerQualified": False},
    }
    save(out / "candidate.json", selection)
    read_release(out / "candidate.json", ROOT)
    verify_source(selection, out / "candidate.json", source)
    print(
        f"Resolved {spec['version']} from its bundle definition; unbuilt and unqualified"
    )


def preflight(version, expected_sha):
    require(
        SEMVER.fullmatch(version) and SHA.fullmatch(expected_sha),
        "invalid release/version commit",
    )
    require(
        os.environ.get("GITHUB_REPOSITORY") == REPOSITORY
        and os.environ.get("GITHUB_REF") == "refs/heads/main",
        "release only from bundle main Action",
    )
    repo = github_json("repos/" + REPOSITORY)
    require(
        repo
        and repo["full_name"] == REPOSITORY
        and repo["private"] is True
        and repo["default_branch"] == "main",
        "unexpected release destination",
    )
    origin = subprocess.check_output(
        ["git", "remote", "get-url", "--push", "origin"], cwd=ROOT, text=True
    ).strip()
    require(
        origin.removesuffix(".git") == f"https://github.com/{REPOSITORY}",
        "unexpected origin",
    )
    actor = os.environ.get("GITHUB_ACTOR")
    current_run = github_json(
        f"repos/{REPOSITORY}/actions/runs/" + os.environ.get("GITHUB_RUN_ID", "")
    )
    require(
        actor
        and current_run
        and current_run["head_sha"] == expected_sha
        and actor
        in (current_run["actor"]["login"], current_run["triggering_actor"]["login"]),
        "publisher workflow identity mismatch",
    )
    head = github_json(f"repos/{REPOSITORY}/git/ref/heads/main")
    require(
        head and head["object"]["sha"] == expected_sha,
        "remote main changed; dispatch against current head",
    )
    require(
        github_json(f"repos/{REPOSITORY}/git/ref/tags/{version}") is None
        and github_json(f"repos/{REPOSITORY}/releases/tags/{version}") is None,
        "version already published; select a new bundle definition",
    )


def verify_handoff(archive, published=True):
    """Exercise the delivered verifier and real charts/renderers before creating a release."""
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        with tarfile.open(archive) as tar:
            require(
                all(m.isfile() for m in tar.getmembers()), "unexpected handoff member"
            )
            for member in tar.getmembers():
                safe_path(root, member.name)
            tar.extractall(root, filter="data")
        dirs = list(root.iterdir())
        require(len(dirs) == 1 and dirs[0].is_dir(), "invalid handoff root")
        artifact = dirs[0]
        run(
            [sys.executable, artifact / "scripts/install.py", "verify"],
            stdout=subprocess.DEVNULL,
        )
        for profile in ("codex", "openclaw"):
            for arch in ("amd64", "arm64"):
                dest = root / (profile + "-" + arch)
                if published:
                    run(
                        [
                            sys.executable,
                            artifact / "scripts/install.py",
                            "render",
                            "--input",
                            artifact / "profiles/aws-example.json",
                            "--profile",
                            profile,
                            "--architecture",
                            "linux/" + arch,
                            "--output",
                            dest,
                        ],
                        stdout=subprocess.DEVNULL,
                    )
                else:
                    # A dry-run exercises the exact renderer without granting installation admission.
                    import install

                    original_root, original_gate = install.ROOT, install.install_gate
                    try:
                        install.ROOT = artifact
                        install.install_gate = lambda release: None
                        install.render(
                            SimpleNamespace(
                                input=artifact / "profiles/aws-example.json",
                                profile=profile,
                                architecture="linux/" + arch,
                                output=dest,
                                mirrors=None,
                            ),
                            read_release(artifact / "release.json"),
                        )
                    finally:
                        install.ROOT, install.install_gate = (
                            original_root,
                            original_gate,
                        )


def finish(args):
    selection = Path(args.selection).resolve()
    release = read_release(selection, ROOT)
    publication = load(selection.parent / "publication.json")
    require(
        publication["status"]
        in ("published-private-unqualified", "checked-unpublished")
        and publication["roles"] == release["images"],
        "shipping publication incomplete",
    )
    # These receipts were bound to this definition and run by the publisher.
    require(
        set(release["qualification"].get("nativeReceipts", {})) == {"amd64", "arm64"},
        "both native receipts required",
    )
    published = publication["status"] == "published-private-unqualified"
    release["distribution"]["published"] = published
    release["kind"] = "release"
    release["qualification"].update(status="native-verified", customerQualified=False)
    save(selection.parent / "release.json", release)
    final = selection.parent / "release.json"
    read_release(final, ROOT)
    out = Path(args.output).resolve()
    out.mkdir(parents=True, exist_ok=True)
    archive = out / "bundle.tar.gz"
    package_args = SimpleNamespace(
        release=final,
        source=args.source,
        dependencies=args.dependencies,
        output=archive,
    )
    package(package_args, release)
    with tempfile.TemporaryDirectory() as temp:
        second = Path(temp) / "bundle.tar.gz"
        package(SimpleNamespace(**(vars(package_args) | {"output": second})), release)
        require(
            archive.read_bytes() == second.read_bytes(), "handoff is not reproducible"
        )
    verify_handoff(archive, published)
    for name in (
        "release.json",
        "bundle.json",
        "publication.json",
        "source-files.json",
        "resolved.json",
    ):
        shutil.copyfile(selection.parent / name, out / name)
    for receipt in release["qualification"]["nativeReceipts"].values():
        shutil.copyfile(selection.parent / receipt["path"], out / receipt["path"])
    save(
        out / "provenance.json",
        {
            "version": release["id"],
            "definitionSha256": release["definitionSha256"],
            "bundleCommit": os.environ.get("GITHUB_SHA"),
            "workflowRun": os.environ.get("GITHUB_RUN_ID"),
            "artifactSha256": digest(archive.read_bytes()),
            "nativeArtifactsVerified": True,
            "published": published,
            "customerQualified": False,
            "files": {
                p.name: digest(p.read_bytes())
                for p in sorted(out.iterdir())
                if p.is_file()
            },
        },
    )
    print(
        "Handoff verified: deterministic archive, complete inventory and four real chart renders"
    )


def publish_release(args):
    out = Path(args.output).resolve()
    provenance = load(out / "provenance.json")
    require(provenance["published"] is True, "cannot publish a dry-run handoff")
    version = provenance["version"]
    sha = os.environ.get("GITHUB_SHA", "")
    require(
        provenance["bundleCommit"] == sha
        and provenance["workflowRun"] == os.environ.get("GITHUB_RUN_ID"),
        "handoff belongs to another build",
    )
    for name, expected in provenance["files"].items():
        require(
            digest(safe_path(out, name).read_bytes()) == expected,
            "handoff changed after verification",
        )
    preflight(version, sha)
    notes = out / "release-notes.txt"
    notes.write_text(
        "Native AMD64 and ARM64 shipping artifacts passed all build and confinement checks. "
        "The archive passed inventory verification, reproducibility and real chart rendering. "
        "Provider access and customer installation acceptance remain separate. "
        "Exact ingredients and evidence are in the attached bundle definition and provenance.\n"
    )
    # Draft holds every asset until the entire upload succeeds. Never replace an existing tag/asset.
    run(
        [
            "gh",
            "release",
            "create",
            version,
            "--repo",
            REPOSITORY,
            "--target",
            sha,
            "--title",
            version,
            "--prerelease",
            "--draft",
            "--notes-file",
            notes,
            *[p for p in sorted(out.iterdir()) if p.is_file() and p != notes],
        ]
    )
    run(["gh", "release", "edit", version, "--repo", REPOSITORY, "--draft=false"])


def latest_definition():
    def version_key(path):
        version = load(path)["version"]
        match = re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)-(alpha|beta|rc)\.(\d+)", version)
        require(match, "invalid version")
        major, minor, patch, phase, number = match.groups()
        return (
            int(major),
            int(minor),
            int(patch),
            {"alpha": 0, "beta": 1, "rc": 2}[phase],
            int(number),
        )

    return max((ROOT / "bundles").glob("*/bundle.json"), key=version_key)


def validate_definitions():
    definitions = list((ROOT / "bundles").glob("*/bundle.json"))
    require(definitions, "no bundle definitions")
    for path in definitions:
        spec, _ = definition(path)
        tag = subprocess.run(
            ["git", "rev-parse", "--verify", "refs/tags/" + spec["version"]],
            capture_output=True,
            text=True,
        )
        if tag.returncode == 0:
            relative = str(path.relative_to(ROOT))
            prior = subprocess.run(
                ["git", "show", spec["version"] + ":" + relative], capture_output=True
            )
            if prior.returncode == 0:
                require(
                    prior.stdout == path.read_bytes(), "published definition changed"
                )
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    event = load(event_path) if event_path else {}
    base = (
        event.get("pull_request", {}).get("base", {}).get("sha")
        or event.get("before")
        or "HEAD"
    )
    if base != "0" * 40:
        changes = subprocess.check_output(
            ["git", "diff", "--name-only", "--diff-filter=MD", base, "--", "releases"],
            cwd=ROOT,
            text=True,
        )
        require(
            not changes.strip(),
            "historical release evidence cannot be modified or deleted",
        )
    print(f"Validated {len(definitions)} definitions and preserved historical evidence")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("resolve")
    p.add_argument("--definition")
    p.add_argument("--output", required=True)
    p.add_argument("--from-git")
    p.add_argument("--dependency-cache")
    sub.add_parser("validate-definitions")
    p = sub.add_parser("preflight")
    p.add_argument("--definition", required=True)
    p = sub.add_parser("finish")
    p.add_argument("--selection", required=True)
    p.add_argument("--source", required=True)
    p.add_argument("--dependencies", required=True)
    p.add_argument("--output", required=True)
    p = sub.add_parser("publish")
    p.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.command == "validate-definitions":
        validate_definitions()
    elif args.command == "preflight":
        spec, _ = definition(args.definition)
        preflight(spec["version"], os.environ.get("GITHUB_SHA", ""))
    else:
        if args.command == "resolve" and not args.definition:
            args.definition = latest_definition()
        {"resolve": resolve, "finish": finish, "publish": publish_release}[
            args.command
        ](args)


if __name__ == "__main__":
    try:
        main()
    except (
        ValueError,
        KeyError,
        IndexError,
        OSError,
        subprocess.CalledProcessError,
    ) as error:
        print(f"release: {error}", file=sys.stderr)
        sys.exit(1)
