#!/usr/bin/env python3
"""Build/release owner CLI; does not deploy infrastructure or Agents."""

import argparse
import gzip
import io
import json
import os
import posixpath
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

from common import (
    ROLES,
    digest,
    identities,
    load,
    read_release,
    release_file,
    require,
    run,
    safe_path,
    save,
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
    runtime = (
        release["runtime"] if release["schemaVersion"] == 2 else release["overlay"]
    )
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


def prepare(args, release):
    dest = Path(args.output).resolve()
    require(not dest.exists(), "source output already exists; choose a new path")
    src = release["sources"]["oce"]
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(args.from_git).resolve() if args.from_git else Path(tmp) / "git"
        if args.from_git:
            remotes = subprocess.check_output(
                ["git", "-C", str(repo), "remote", "-v"], text=True
            )
            require(
                src["repository"] in remotes,
                "local object repository lacks selected source remote",
            )
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
        archive = subprocess.check_output(
            ["git", "-C", str(repo), "archive", "--format=tar", src["commit"]]
        )
        require(
            digest(archive) == src["archiveSha256"], "source archive checksum mismatch"
        )
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            require(
                all(m.isfile() or m.isdir() for m in tar.getmembers()),
                "unexpected source archive member",
            )
            for m in tar.getmembers():
                safe_path(dest, m.name)
            dest.mkdir(parents=True)
            tar.extractall(dest, filter="data")
    verify_source(release, args.release, dest)
    print(f"Pinned source exported: {dest}")


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
    files["upstream/deploy/profiles/codex.json"] = (
        release_file(args.release, ROOT, "defaults/codex-profile.json").read_bytes(),
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
    if release["schemaVersion"] == 1:
        copy["overlay"]["files"] = {
            k: v for k, v in release["overlay"]["files"].items()
        }  # provenance, not delivered build inputs
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


def ecr_destination(prefix, release):
    match = re.fullmatch(
        r"(\d{12})\.dkr\.ecr\.([a-z0-9-]+)\.amazonaws\.com/([a-z0-9][a-z0-9/_-]*)",
        prefix,
    )
    require(match is not None, "push/mirror destination must be private AWS ECR")
    account, region, path = match.groups()
    identity = json.loads(
        subprocess.check_output(
            ["aws", "sts", "get-caller-identity", "--region", region]
        )
    )
    require(identity["Account"] == account, "AWS identity/destination account mismatch")
    for role in ROLES:
        repo = (
            path
            + "/"
            + ("repository-credentials" if role == "repositoryCredentials" else role)
        )
        entry = json.loads(
            subprocess.check_output(
                [
                    "aws",
                    "ecr",
                    "describe-repositories",
                    "--region",
                    region,
                    "--registry-id",
                    account,
                    "--repository-names",
                    repo,
                ]
            )
        )["repositories"][0]
        require(
            entry["imageTagMutability"] == "IMMUTABLE"
            and not entry.get("imageTagMutabilityExclusionFilters"),
            "destination must enforce immutable tags without exclusions",
        )
        result = subprocess.run(
            [
                "aws",
                "ecr",
                "describe-images",
                "--region",
                region,
                "--registry-id",
                account,
                "--repository-name",
                repo,
                "--image-ids",
                "imageTag=" + release["id"],
            ],
            capture_output=True,
            text=True,
        )
        require(
            result.returncode != 0 and "ImageNotFoundException" in result.stderr,
            "destination tag exists or absence could not be verified",
        )
    return account, region


def build(args, release):
    verify_source(release, args.release, Path(args.source))
    require(release["kind"] == "candidate", "build requires a new candidate identity")
    out = Path(args.output).resolve()
    require(not out.exists(), "build output exists")
    if args.push:
        ecr_destination(args.registry_prefix, release)
    else:
        driver = subprocess.check_output(
            ["docker", "buildx", "inspect", "default"], text=True
        )
        require(
            re.search(r"^Driver:\s+docker$", driver, re.MULTILINE),
            "local builds require Docker default engine builder",
        )
        require(
            args.registry_prefix == "bundle.local/oce",
            "local builds use bundle.local/oce (no publication)",
        )
    out.mkdir(parents=True)
    refs = {}
    metadata = {}
    for role in ROLES:
        recipe = release["build"][role]
        tag = (
            args.registry_prefix
            + "/"
            + ("repository-credentials" if role == "repositoryCredentials" else role)
            + ":"
            + release["id"]
        )
        target_tag = tag + "-base" if role == "runtime" else tag
        meta = out / (role + "-build.json")
        cmd = [
            "docker",
            "buildx",
            "build",
            *(["--builder", "default"] if not args.push else []),
            "--push" if args.push else "--load",
            "--platform",
            release["architecture"],
            "--provenance=mode=min" if args.push else "--provenance=false",
            "--metadata-file",
            meta,
            "-f",
            Path(args.source) / recipe["dockerfile"],
            "--target",
            recipe["target"],
            "--build-arg",
            "NODE_BASE_IMAGE=" + release["build"]["nodeBaseImage"],
            "--build-arg",
            "NODE_RUNTIME_BASE_IMAGE=" + release["build"]["nodeRuntimeBaseImage"],
            "--build-arg",
            "OPENCLAW_COMMIT=" + release["sources"]["openclaw"]["commit"],
            "--build-arg",
            "OCC_BUILD_REVISION=" + release["sources"]["oce"]["commit"],
            "--label",
            "org.opencontainers.image.revision=" + release["sources"]["oce"]["commit"],
            "-t",
            target_tag,
            args.source,
        ]
        run(cmd)
        if role == "runtime":
            # Local engine tag is checked against its recorded image ID; push uses an immutable manifest digest.
            if args.push:
                base = (
                    args.registry_prefix
                    + "/runtime@"
                    + load(meta)["containerimage.digest"]
                )
            else:
                base = target_tag
                base_id = subprocess.check_output(
                    ["docker", "image", "inspect", "--format", "{{.Id}}", target_tag],
                    text=True,
                ).strip()
            with tempfile.TemporaryDirectory() as tmp:
                context = Path(tmp)
                shutil.copytree(
                    ROOT / release["overlay"]["directory"], context / "overlays/codex"
                )
                (context / "upstream").mkdir()
                shutil.copyfile(
                    Path(args.source) / release["overlay"]["inventoryHelper"],
                    context / "upstream/build-runtime-assets.mjs",
                )
                meta = out / "runtime-overlay-build.json"
                run(
                    [
                        "docker",
                        "buildx",
                        "build",
                        *(["--builder", "default"] if not args.push else []),
                        "--push" if args.push else "--load",
                        "--platform",
                        release["architecture"],
                        "--provenance=mode=min" if args.push else "--provenance=false",
                        "--metadata-file",
                        meta,
                        "--build-arg",
                        "BASE_RUNTIME=" + base,
                        "--build-arg",
                        "NODE_BASE_IMAGE=" + release["build"]["nodeBaseImage"],
                        "--label",
                        "org.opencontainers.image.revision="
                        + release["sources"]["oce"]["commit"],
                        "-f",
                        context / "overlays/codex/Dockerfile",
                        "-t",
                        tag,
                        context,
                    ]
                )
        if role == "runtime" and not args.push:
            require(
                subprocess.check_output(
                    ["docker", "image", "inspect", "--format", "{{.Id}}", target_tag],
                    text=True,
                ).strip()
                == base_id,
                "local runtime base changed during overlay build",
            )
        metadata[role] = load(meta)
        if args.push:
            dg = metadata[role]["containerimage.digest"]
            require(
                re.fullmatch(r"sha256:[a-f0-9]{64}", dg) is not None,
                "missing build manifest digest",
            )
            refs[role] = tag.split(":")[0] + "@" + dg
        else:
            refs[role] = tag
    save(
        out / "build-record.json",
        {
            "status": "unqualified",
            "releaseId": release["id"],
            "oceCommit": release["sources"]["oce"]["commit"],
            "openclawCommit": release["sources"]["openclaw"]["commit"],
            "architecture": release["architecture"],
            "references": refs,
            "metadata": metadata,
            "overlay": release["overlay"],
        },
    )
    if args.push:
        candidate = json.loads(json.dumps(release))
        candidate.pop("candidateImages", None)
        for role in ROLES:
            candidate["images"][role]["reference"] = refs[role]
        save(out / "candidate.json", candidate)
        shutil.copyfile(
            Path(args.release).parent / release["sources"]["oce"]["files"],
            out / release["sources"]["oce"]["files"],
        )
    print(f"Build record: {out / 'build-record.json'}; UNQUALIFIED")


def candidate(args, release):
    out = Path(args.output)
    require(not out.exists(), "candidate file exists")
    new = json.loads(json.dumps(release))
    new["id"] = args.id
    new["kind"] = "candidate"
    new["baselineEvidence"] = new["qualification"]
    new["qualification"] = {
        "status": "unqualified",
        "customerQualified": False,
        "availability": "not-checked",
    }
    # Existing digests remain input provenance only until build replaces all three.
    new["candidateImages"] = (
        "inherited references; must replace with build outputs before qualification"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    save(out, new)
    target_inventory = out.parent / new["sources"]["oce"]["files"]
    if (
        target_inventory.resolve()
        != (Path(args.release).parent / new["sources"]["oce"]["files"]).resolve()
    ):
        require(not target_inventory.exists(), "source inventory output exists")
        shutil.copyfile(
            Path(args.release).parent / new["sources"]["oce"]["files"], target_inventory
        )
    read_release(out, ROOT)
    print(f"Candidate: {out}; UNQUALIFIED")


def check_images(args, release):
    out = Path(args.output)
    require(not out.exists(), "image check output exists")
    receipt = {
        "status": "failed",
        "images": identities(release),
        "oceCommit": release["sources"]["oce"]["commit"],
        "openclawCommit": release["sources"]["openclaw"]["commit"],
        "architecture": release["architecture"],
        "checks": {},
    }
    try:
        for role, ref in identities(release).items():
            run(
                ["docker", "pull", "--platform", release["architecture"], ref],
                stdout=subprocess.DEVNULL,
            )
            info = json.loads(
                subprocess.check_output(["docker", "image", "inspect", ref])
            )[0]
            require(
                info["Os"] + "/" + info["Architecture"] == release["architecture"],
                "image architecture mismatch",
            )
            require(
                info["Config"]["Labels"].get("org.opencontainers.image.revision")
                == release["sources"]["oce"]["commit"],
                f"{role} OCI source label mismatch",
            )
            if role == "runtime":
                proof = json.loads(
                    subprocess.check_output(
                        [
                            "docker",
                            "run",
                            "--rm",
                            "--network",
                            "none",
                            "--entrypoint",
                            "node",
                            ref,
                            "-e",
                            'const fs=require("fs");console.log(JSON.stringify({provenance:JSON.parse(fs.readFileSync("/opt/oce/runtime/provenance.json")),build:JSON.parse(fs.readFileSync("/opt/oce/runtime/build.json")),codex:require("child_process").execFileSync("codex",["--version"],{encoding:"utf8"}).trim()}))',
                        ]
                    )
                )
                require(
                    proof["build"]["commit"] == release["sources"]["oce"]["commit"],
                    "runtime OCE provenance mismatch",
                )
                require(
                    proof["provenance"]["commit"]
                    == release["sources"]["openclaw"]["commit"]
                    and proof["provenance"]["sourceArchiveSha256"]
                    == release["sources"]["openclaw"]["archiveSha256"],
                    "runtime OpenClaw provenance mismatch",
                )
                require(
                    proof["codex"] == "codex-cli " + release["overlay"]["codexVersion"],
                    "runtime Codex mismatch",
                )
                receipt["checks"][role] = proof
            else:
                receipt["checks"][role] = {
                    "architecture": "linux/amd64",
                    "sourceLabel": True,
                }
        receipt["status"] = "passed-identity-only"
    finally:
        out.parent.mkdir(parents=True, exist_ok=True)
        save(out, receipt)
    print(f"Identity receipt: {out}; this is not runtime qualification")


def qualify(args, release):
    require(
        release["kind"] == "candidate" and not release.get("candidateImages"),
        "qualification requires built candidate digests",
    )
    verify_source(release, args.release, Path(args.source))
    require(
        sys.platform == "linux" and os.uname().machine == "x86_64",
        "qualification requires native Linux AMD64 host",
    )
    require(
        subprocess.check_output(
            ["docker", "info", "--format", "{{.OSType}}/{{.Architecture}}"], text=True
        ).strip()
        == "linux/x86_64",
        "qualification requires native AMD64 Docker",
    )
    require(
        digest(Path(args.seccomp).read_bytes()) == release["seccomp"]["sha256"],
        "qualification seccomp mismatch",
    )
    out = Path(args.output).resolve()
    require(not out.exists(), "qualification output exists")
    out.mkdir(parents=True)
    check_images(argparse.Namespace(output=out / "identity.json"), release)
    receipt = {
        "status": "failed",
        "images": identities(release),
        "oceCommit": release["sources"]["oce"]["commit"],
        "openclawCommit": release["sources"]["openclaw"]["commit"],
        "codexVersion": release["overlay"]["codexVersion"],
        "architecture": release["architecture"],
        "seccompSha256": release["seccomp"]["sha256"],
        "qualificationPatchSha256": release["overlay"]["files"][
            release["overlay"]["qualificationPatch"]
        ],
        "scope": "controller/runtime image tests and actual credential service isolation; no real cloud/provider/installation acceptance",
    }
    try:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "oce"
            shutil.copytree(args.source, source)
            run(
                [
                    "git",
                    "apply",
                    "--check",
                    ROOT / release["overlay"]["qualificationPatch"],
                ],
                cwd=source,
            )
            run(
                ["git", "apply", ROOT / release["overlay"]["qualificationPatch"]],
                cwd=source,
            )
            run(["corepack", "pnpm", "install", "--frozen-lockfile"], cwd=source)
            run(["corepack", "pnpm", "credentials:build"], cwd=source)
            client = "bundle.local/qualification-client:" + release["id"]
            fixture = "bundle.local/qualification-fixture:" + release["id"]
            run(
                [
                    "docker",
                    "build",
                    "--builder",
                    "default",
                    "--load",
                    "--pull=false",
                    "-f",
                    source / "deploy/runtime/repository-credentials/Dockerfile.client",
                    "-t",
                    client,
                    source / ".build/repository-credentials/client",
                ]
            )
            run(
                [
                    "docker",
                    "build",
                    "--builder",
                    "default",
                    "--load",
                    "--pull=false",
                    "-f",
                    source
                    / "tests/fixtures/repository-credentials/Dockerfile.qualification",
                    "--build-arg",
                    "SERVICE_IMAGE="
                    + release["images"]["repositoryCredentials"]["reference"],
                    "--build-arg",
                    "CLIENT_IMAGE=" + client,
                    "-t",
                    fixture,
                    source,
                ]
            )
            env = dict(
                os.environ,
                REPOSITORY_CREDENTIALS_SERVICE_IMAGE=release["images"][
                    "repositoryCredentials"
                ]["reference"],
                REPOSITORY_CREDENTIALS_CLIENT_IMAGE=client,
                REPOSITORY_CREDENTIALS_NODE_IMAGE=fixture,
                REPOSITORY_CREDENTIALS_TEST_IMAGE=fixture,
                OCC_TEST_PRODUCTION_IMAGE=release["images"]["controller"]["reference"],
                OCC_TEST_RUNTIME_IMAGE=release["images"]["runtime"]["reference"],
                OCC_TEST_CODEX_SECCOMP_PROFILE=str(Path(args.seccomp).resolve()),
            )
            tests = [
                "production-image-startup",
                "runtime-image-startup",
                "runtime-image-startup-probe",
                "repository-runtime-volume",
                "repository-credentials-isolation",
            ]
            # Private TAP output can include synthetic credentials; never ship raw logs.
            os.chmod(out, 0o700)
            with (out / "checks.tap").open("w") as log:
                result = subprocess.run(
                    [
                        "node",
                        "--test",
                        "--test-concurrency=1",
                        "--test-reporter=tap",
                        *[f"tests/integration/{t}.test.mjs" for t in tests],
                    ],
                    cwd=source,
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                )
            text = (out / "checks.tap").read_text()
            counts = {
                k: int(re.findall(r"^# " + k + r" (\d+)$", text, re.MULTILINE)[-1])
                for k in ("tests", "pass", "fail", "skipped", "cancelled")
            }
            require(
                result.returncode == 0
                and counts["tests"] > 0
                and counts["pass"] == counts["tests"]
                and all(counts[k] == 0 for k in ("fail", "skipped", "cancelled")),
                "runtime qualification failed or skipped tests",
            )
            receipt.update(
                status="passed",
                counts=counts,
                tapSha256=digest(text.encode()),
                hostUid=os.getuid(),
            )
    finally:
        save(out / "qualification.json", receipt)
    print(
        f"Receipt: {out / 'qualification.json'}; release selection remains unqualified pending review"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate")
    p = sub.add_parser("source")
    p.add_argument("--from-git")
    p.add_argument("--output", required=True)
    p = sub.add_parser("package")
    p.add_argument("--source", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--dependencies")
    p = sub.add_parser("candidate")
    p.add_argument("--id", required=True)
    p.add_argument("--output", required=True)
    p = sub.add_parser("build")
    p.add_argument("--source", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--registry-prefix", default="bundle.local/oce")
    p.add_argument("--push", action="store_true")
    p = sub.add_parser("check-images")
    p.add_argument("--output", required=True)
    p = sub.add_parser("qualify")
    p.add_argument("--source", required=True)
    p.add_argument("--seccomp", required=True)
    p.add_argument("--output", required=True)
    args = parser.parse_args()
    release = read_release(args.release, ROOT)
    if args.command == "validate":
        source_files(release, args.release)
        print(f"{release['id']}: valid ({release['qualification']['status']})")
    else:
        require(
            release["schemaVersion"] == 1 or args.command in ("source", "package"),
            "stock candidates use scripts/stock.py for native builds and checks",
        )
        if release["schemaVersion"] == 2 and args.command == "package":
            require(
                args.dependencies,
                "stock package requires verified renderer dependency archives",
            )
        (
            prepare
            if args.command == "source"
            else globals()[args.command.replace("-", "_")]
        )(args, release)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as error:
        print(f"bundle: {error}", file=sys.stderr)
        sys.exit(1)
