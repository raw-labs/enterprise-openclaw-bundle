#!/usr/bin/env python3
"""Stock multi-platform build/export and private candidate publication; no deployment."""

import argparse
import base64
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from bundle import prepare, source_files, verify_source
from common import (
    ROLES,
    digest,
    load,
    read_release,
    require,
    run,
    safe_path,
    save,
    validate,
    verify_files,
)

ROOT = Path(__file__).resolve().parents[1]
ROLE_NAMES = {"repositoryCredentials": "repository-credentials"}
DIGEST = re.compile(r"sha256:[a-f0-9]{64}$")


def new(args):
    checkpoint = load(args.checkpoint)
    require(
        checkpoint["recordType"] == "source-checkpoint", "expected source checkpoint"
    )
    out = Path(args.output).resolve()
    require(not out.exists(), "candidate output exists")
    images = {
        role: {
            "reference": None,
            "platforms": {},
            "oceCommit": checkpoint["sources"]["oce"]["commit"],
        }
        for role in ROLES
    }
    images["runtime"].update(
        openclawCommit=checkpoint["sources"]["openclaw"]["commit"],
        codexVersion=checkpoint["runtime"]["codexVersion"],
    )
    payload = {
        str(p.relative_to(ROOT)): digest(p.read_bytes())
        for directory in ("defaults",)
        for p in sorted((ROOT / directory).rglob("*"))
        if p.is_file()
    }
    payload["profiles/aws-example.json"] = digest(
        (ROOT / "profiles/aws-example.json").read_bytes()
    )
    release = {
        "schemaVersion": 2,
        "id": args.id,
        "kind": "candidate",
        "architectures": checkpoint["targetArchitectures"],
        "sources": checkpoint["sources"],
        "chart": checkpoint["chart"],
        "runtime": checkpoint["runtime"],
        "build": {k: v for k, v in checkpoint["build"].items() if k != "recipes"}
        | checkpoint["build"]["recipes"],
        "distribution": checkpoint["distribution"] | {"productVersion": args.id},
        "rendererDependencies": checkpoint["rendererDependencies"],
        "images": images,
        "seccomp": {"profiles": {}},
        "payloadFiles": payload,
        "qualification": {"status": "unqualified", "customerQualified": False},
        "checkpointSha256": digest(Path(args.checkpoint).read_bytes()),
    }
    validate(release)
    release["build"]["noticeLayer"] = {
        "fragment": "overlays/notices.fragment",
        "sha256": digest((ROOT / "overlays/notices.fragment").read_bytes()),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    inventory = safe_path(
        Path(args.checkpoint).parent, checkpoint["sources"]["oce"]["files"]
    )
    require(
        digest(inventory.read_bytes()) == checkpoint["sources"]["oce"]["filesSha256"],
        "checkpoint inventory mismatch",
    )
    target = safe_path(out.parent, release["sources"]["oce"]["files"])
    if target != inventory.resolve():
        require(
            not target.exists() or target.read_bytes() == inventory.read_bytes(),
            "inventory output differs",
        )
        shutil.copyfile(inventory, target)
    save(out, release)
    print(f"Unbuilt, unqualified stock candidate: {out}")


def dependency_bytes(release, directory):
    for name, package in release["rendererDependencies"].items():
        path = directory / f"{name}-{package['version']}.tgz"
        data = path.read_bytes()
        integrity = "sha512-" + base64.b64encode(hashlib.sha512(data).digest()).decode()
        require(
            digest(data) == package["archiveSha256"]
            and integrity == package["integrity"],
            "renderer dependency archive mismatch",
        )
        yield name, package, data


def dependencies(args, release):
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    for name, package in release["rendererDependencies"].items():
        path = out / f"{name}-{package['version']}.tgz"
        if not path.exists():
            url = f"https://registry.npmjs.org/{name}/-/{name}-{package['version']}.tgz"
            with urllib.request.urlopen(url, timeout=120) as response:
                data = response.read()
            require(
                digest(data) == package["archiveSha256"],
                "downloaded renderer checksum mismatch",
            )
            path.write_bytes(data)
    list(dependency_bytes(release, out))
    print("Pinned renderer dependency archives verified")


def renderer_files(release, directory):
    files = {}
    for name, package, data in dependency_bytes(release, directory):
        prefix = "upstream/apps/controller/node_modules/" + name + "/"
        with tarfile.open(fileobj=io.BytesIO(data)) as tar:
            require(
                all(m.isfile() or m.isdir() for m in tar.getmembers()),
                "unexpected npm archive member",
            )
            members = {m.name: m for m in tar.getmembers() if m.isfile()}
            metadata = json.loads(
                tar.extractfile(members["package/package.json"]).read()
            )
            require(
                metadata["name"] == name and metadata["version"] == package["version"],
                "npm package identity mismatch",
            )
            for path, member in members.items():
                require(path.startswith("package/"), "invalid npm package root")
                relative = path.removeprefix("package/")
                safe_path(directory, relative)
                if relative in ("package.json", "LICENSE") or relative.startswith(
                    "dist/cjs/"
                ):
                    files[prefix + relative] = (tar.extractfile(member).read(), 0o644)
            require(prefix + "LICENSE" in files, "renderer license missing")
    return files


def native_arch(arch):
    require(sys.platform == "linux", "native builds/checks require Linux")
    host = {"x86_64": "amd64", "aarch64": "arm64", "arm64": "arm64"}.get(
        os.uname().machine
    )
    require(host == arch, "target must match the native host architecture")
    docker = subprocess.check_output(
        ["docker", "info", "--format", "{{.OSType}}/{{.Architecture}}"], text=True
    ).strip()
    require(
        docker
        in (f"linux/{arch}", "linux/x86_64" if arch == "amd64" else "linux/aarch64"),
        "Docker target is not native",
    )


def inspect_oci(directory, platform, source_sha):
    root = load(directory / "index.json")
    require(len(root["manifests"]) == 1, "expected exactly one native export")
    descriptor = root["manifests"][0]

    def blob(entry):
        require(DIGEST.fullmatch(entry["digest"]), "invalid OCI digest")
        data = (directory / "blobs/sha256" / entry["digest"].split(":")[1]).read_bytes()
        require(
            "sha256:" + digest(data) == entry["digest"] and len(data) == entry["size"],
            "OCI blob mismatch",
        )
        return json.loads(data)

    manifest = blob(descriptor)
    require(
        manifest["mediaType"] == "application/vnd.oci.image.manifest.v1+json",
        "expected a native OCI manifest without attestations",
    )
    config = blob(manifest["config"])
    require(
        config["os"] + "/" + config["architecture"] == platform,
        "export architecture mismatch",
    )
    labels = config["config"].get("Labels") or {}
    require(
        labels.get("org.opencontainers.image.revision") == source_sha,
        "OCI source revision mismatch",
    )
    require(
        labels.get("org.opencontainers.image.source")
        == "https://github.com/raw-labs/enterprise-openclaw-bundle",
        "OCI package ownership mismatch",
    )
    for layer in manifest["layers"]:
        require(DIGEST.fullmatch(layer["digest"]), "invalid layer digest")
        path = directory / "blobs/sha256" / layer["digest"].split(":")[1]
        hasher = hashlib.sha256()
        with path.open("rb") as file:
            while data := file.read(1024 * 1024):
                hasher.update(data)
        require(
            "sha256:" + hasher.hexdigest() == layer["digest"]
            and path.stat().st_size == layer["size"],
            "OCI layer mismatch",
        )
    return {
        "digest": descriptor["digest"],
        "configDigest": manifest["config"]["digest"],
    }


def build(args, release):
    native_arch(args.arch)
    verify_source(release, args.selection, Path(args.source))
    require(
        (os.cpu_count() or 0) >= 4
        and os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE") >= 12 * 1024**3,
        "native build requires at least 4 CPUs and 12 GiB memory",
    )
    out = Path(args.output).resolve()
    require(not out.exists(), "build output exists")
    out.mkdir(parents=True)
    record = {
        "status": "unqualified",
        "releaseId": release["id"],
        "platform": "linux/" + args.arch,
        "oceCommit": release["sources"]["oce"]["commit"],
        "images": {},
    }
    for role in ROLES:
        recipe = release["build"][role]
        cmd = [
            "docker",
            "buildx",
            "build",
            "--platform",
            record["platform"],
            "--provenance=false",
            "--output",
            f"type=oci,dest={out / role},tar=false,rewrite-timestamp=true",
            "--metadata-file",
            out / (role + "-build.json"),
            "-f",
            Path(args.source) / recipe["dockerfile"],
            "--target",
            recipe["target"],
        ]
        for key, value in {
            "NODE_BASE_IMAGE": release["build"]["nodeBaseImage"],
            "NODE_RUNTIME_BASE_IMAGE": release["build"]["nodeRuntimeBaseImage"],
            "OPENCLAW_COMMIT": release["sources"]["openclaw"]["commit"],
            "OCC_BUILD_REVISION": record["oceCommit"],
            "SOURCE_DATE_EPOCH": release["sources"]["oce"]["commitEpoch"],
        }.items():
            cmd.extend(["--build-arg", f"{key}={value}"])
        cmd.extend(
            [
                "--label",
                "org.opencontainers.image.source=https://github.com/raw-labs/enterprise-openclaw-bundle",
                "--label",
                "org.opencontainers.image.revision=" + record["oceCommit"],
            ]
        )
        if args.gha_cache:
            scope = ROLE_NAMES.get(role, role) + "-" + args.arch
            cmd.extend(
                [
                    "--cache-from",
                    "type=gha,scope=" + scope,
                    "--cache-to",
                    "type=gha,mode=max,scope=" + scope,
                ]
            )
        notice = release["build"]["noticeLayer"]
        fragment = safe_path(ROOT, notice["fragment"]).read_bytes()
        require(digest(fragment) == notice["sha256"], "notice layer input mismatch")
        # Preserve the selected recipe and append only the required upstream notice.
        with tempfile.TemporaryDirectory() as temporary:
            dockerfile = Path(temporary) / "Dockerfile"
            dockerfile.write_bytes(
                (Path(args.source) / recipe["dockerfile"]).read_bytes()
                + fragment.replace(b"__UPSTREAM_TARGET__", recipe["target"].encode())
            )
            cmd[cmd.index("-f") + 1] = dockerfile
            cmd[cmd.index("--target") + 1] = "bundle-notices"
            run([*cmd, args.source])
        record["images"][role] = inspect_oci(
            out / role, record["platform"], record["oceCommit"]
        )
        require(
            record["images"][role]["digest"]
            == load(out / (role + "-build.json"))["containerimage.digest"],
            "builder/export digest mismatch",
        )
    verify_source(release, args.selection, Path(args.source))
    save(out / "build-record.json", record)
    print("Three native exports built; UNQUALIFIED")


def tap_counts(text):
    counts = {
        key: int(re.findall(r"^# " + key + r" (\d+)$", text, re.MULTILINE)[-1])
        for key in ("tests", "pass", "fail", "skipped", "cancelled")
    }
    require(
        counts["tests"] > 0
        and counts["pass"] == counts["tests"]
        and all(counts[k] == 0 for k in ("fail", "skipped", "cancelled")),
        "tests failed or skipped",
    )
    return counts


def tests(command, source, env, log):
    with log.open("w") as file:
        os.chmod(log, 0o600)
        result = subprocess.run(
            [str(a) for a in command],
            cwd=source,
            env=env,
            stdout=file,
            stderr=subprocess.STDOUT,
        )
    require(result.returncode == 0, f"native lane failed; private diagnostics: {log}")
    return tap_counts(log.read_text())


def check(args, release):
    native_arch(args.arch)
    out = Path(args.build).resolve()
    source = Path(args.source).resolve()
    verify_files(source, source_files(release, args.selection))
    record = load(out / "build-record.json")
    require(
        record["releaseId"] == release["id"]
        and record["oceCommit"] == release["sources"]["oce"]["commit"]
        and record["platform"] == "linux/" + args.arch,
        "build selection mismatch",
    )
    report = out / "proof"
    require(not report.exists(), "check output exists")
    report.mkdir(mode=0o700)
    logs = Path(args.logs).resolve()
    require(not logs.exists(), "private log output exists")
    logs.mkdir(parents=True, mode=0o700)
    images = {}
    tags = []
    receipt = {
        "status": "failed",
        "releaseId": release["id"],
        "oceCommit": record["oceCommit"],
        "openclawCommit": release["sources"]["openclaw"]["commit"],
        "codexVersion": release["runtime"]["codexVersion"],
        "platform": record["platform"],
        "native": True,
        "workflow": {
            key: os.environ.get(key)
            for key in (
                "GITHUB_REPOSITORY",
                "GITHUB_SHA",
                "GITHUB_RUN_ID",
                "GITHUB_RUN_ATTEMPT",
            )
        },
        "images": record["images"],
        "lanes": {},
        "scope": "native shipping export tests; no provider workflow or customer installation qualification",
    }
    env = dict(os.environ)
    try:
        for role in ROLES:
            identity = inspect_oci(out / role, record["platform"], record["oceCommit"])
            require(identity == record["images"][role], "built OCI identity changed")
            tag = f"localhost/bundle-{ROLE_NAMES.get(role, role)}:{release['id']}-{args.arch}"
            existing = subprocess.run(
                ["docker", "image", "inspect", tag],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            require(existing.returncode != 0, "local export tag already exists")
            run(
                ["skopeo", "copy", "oci:" + str(out / role), "docker-daemon:" + tag],
                stdout=subprocess.DEVNULL,
            )
            info = json.loads(
                subprocess.check_output(["docker", "image", "inspect", tag])
            )[0]
            require(
                info["Id"] == identity["configDigest"],
                "loaded config differs from tested export",
            )
            images[role] = info["Id"]
            tags.append(tag)
            notice = subprocess.check_output(
                [
                    "docker",
                    "run",
                    "--rm",
                    "--network",
                    "none",
                    "--read-only",
                    "--user",
                    "1000:1000",
                    "--cap-drop",
                    "ALL",
                    "--security-opt",
                    "no-new-privileges",
                    "--entrypoint",
                    "node",
                    info["Id"],
                    "-e",
                    'process.stdout.write(require("node:fs").readFileSync("/usr/share/licenses/openclaw-enterprise/LICENSE"))',
                ]
            )
            require(
                digest(notice) == source_files(release, args.selection)["LICENSE"],
                "shipping upstream notice mismatch",
            )
        node = ["node", "--test", "--test-concurrency=1", "--test-reporter=tap"]
        receipt["lanes"]["controller"] = tests(
            [*node, "tests/integration/production-image-startup.test.mjs"],
            source,
            dict(env, OCC_TEST_PRODUCTION_IMAGE=images["controller"]),
            logs / "controller.tap",
        )
        state = (
            Path(env.get("RUNNER_TEMP", tempfile.gettempdir()))
            / f"bundle-runtime-{args.arch}.json"
        )
        receipt["lanes"]["runtime"] = tests(
            [
                "node",
                ROOT / "scripts/stock-smoke.mjs",
                source,
                images["runtime"],
                state,
                report,
            ],
            source,
            env,
            logs / "runtime.tap",
        )
        require(not state.exists(), "runtime cleanup incomplete")
        receipt["confinement"] = load(report / "confinement.json")
        receipt["confinement"]["reviewedInputs"] = {
            p: digest((source / p).read_bytes())
            for p in (
                "scripts/lib/codex-seccomp-profile.mjs",
                ".github/actions/run-ci-lane/codex-sandbox.apparmor",
            )
        }
        require(
            digest((report / "codex-seccomp.json").read_bytes())
            == receipt["confinement"]["seccompSha256"],
            "confinement proof mismatch",
        )
        run(
            ["corepack", "pnpm", "credentials:build"],
            cwd=source,
            stdout=subprocess.DEVNULL,
        )
        client = f"localhost/bundle-check-client:{release['id']}-{args.arch}"
        run(
            [
                "docker",
                "buildx",
                "build",
                "--builder",
                "default",
                "--load",
                "--platform",
                record["platform"],
                "-f",
                source / "deploy/runtime/repository-credentials/Dockerfile.client",
                "-t",
                client,
                source / ".build/repository-credentials/client",
            ],
            stdout=subprocess.DEVNULL,
        )
        tags.append(client)
        receipt["lanes"]["repositoryCredentials"] = tests(
            [
                *node,
                "tests/integration/repository-runtime-volume.test.mjs",
                "tests/integration/repository-credentials-isolation.test.mjs",
            ],
            source,
            dict(
                env,
                OCC_TEST_RUNTIME_IMAGE=images["runtime"],
                REPOSITORY_CREDENTIALS_SERVICE_IMAGE=images["repositoryCredentials"],
                REPOSITORY_CREDENTIALS_CLIENT_IMAGE=client,
            ),
            logs / "repository.tap",
        )
        for role in ROLES:
            require(
                inspect_oci(out / role, record["platform"], record["oceCommit"])
                == record["images"][role],
                "export changed during qualification",
            )
        verify_files(source, source_files(release, args.selection))
        receipt["status"] = "passed-native-export-checks"
    finally:
        for tag in reversed(tags):
            run(["docker", "image", "rm", tag], stdout=subprocess.DEVNULL)
        receipt["cleanup"] = "completed"
        receipt["logSha256"] = {
            p.name: digest(p.read_bytes()) for p in logs.glob("*.tap")
        }
        save(report / "native-receipt.json", receipt)
    print(
        "Native export checks passed without skips; release remains unqualified pending review"
    )


def verify_receipt(receipt, release, arch, identities):
    require(
        receipt["status"] == "passed-native-export-checks"
        and receipt["cleanup"] == "completed"
        and receipt["native"] is True
        and receipt["platform"] == "linux/" + arch
        and receipt["releaseId"] == release["id"]
        and receipt["images"] == identities
        and receipt["oceCommit"] == release["sources"]["oce"]["commit"]
        and receipt["openclawCommit"] == release["sources"]["openclaw"]["commit"]
        and receipt["codexVersion"] == release["runtime"]["codexVersion"],
        "native receipt identity mismatch",
    )
    require(set(receipt["lanes"]) == set(ROLES), "all native lanes required")
    for counts in receipt["lanes"].values():
        require(
            counts["tests"] > 0
            and counts["pass"] == counts["tests"]
            and all(counts[k] == 0 for k in ("fail", "skipped", "cancelled")),
            "native receipt has failed or skipped tests",
        )


def assemble_index(directory, exports, version):
    """An index references exactly the two manifests which native checks executed."""
    directory.mkdir(parents=True)
    (directory / "blobs/sha256").mkdir(parents=True)
    manifests = []
    for arch, export in sorted(exports.items()):
        descriptor = load(export / "index.json")["manifests"][0]
        descriptor = {k: descriptor[k] for k in ("mediaType", "digest", "size")}
        descriptor["platform"] = {"os": "linux", "architecture": arch}
        manifests.append(descriptor)
        for blob in (export / "blobs/sha256").iterdir():
            target = directory / "blobs/sha256" / blob.name
            if not target.exists():
                shutil.copyfile(blob, target)
    index = {
        "schemaVersion": 2,
        "mediaType": "application/vnd.oci.image.index.v1+json",
        "manifests": manifests,
    }
    data = (json.dumps(index, sort_keys=True, separators=(",", ":")) + "\n").encode()
    dg = "sha256:" + digest(data)
    (directory / "blobs/sha256" / dg.split(":")[1]).write_bytes(data)
    save(directory / "oci-layout", {"imageLayoutVersion": "1.0.0"})
    save(
        directory / "index.json",
        {
            "schemaVersion": 2,
            "manifests": [
                {
                    "mediaType": index["mediaType"],
                    "digest": dg,
                    "size": len(data),
                    "annotations": {"org.opencontainers.image.ref.name": version},
                }
            ],
        },
    )
    return dg


def github_json(path):
    token = os.environ.get("GH_TOKEN")
    require(token, "publication requires the repository workflow token")
    request = urllib.request.Request(
        "https://api.github.com/" + path,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise ValueError("GitHub publication access check failed") from None


def private_package(name):
    from urllib.parse import quote

    package = github_json("orgs/raw-labs/packages/container/" + quote(name, safe=""))
    if package is not None:
        require(
            package["visibility"] == "private"
            and package.get("repository", {}).get("full_name")
            == "raw-labs/enterprise-openclaw-bundle",
            "package is public or belongs to another repository",
        )
    return package


def publish(args, release):
    require(
        os.environ.get("GITHUB_REPOSITORY") == "raw-labs/enterprise-openclaw-bundle"
        and os.environ.get("GITHUB_REF") == "refs/heads/main",
        "publication only from private bundle main workflow",
    )
    repo = github_json("repos/raw-labs/enterprise-openclaw-bundle")
    require(
        repo and repo["private"] is True and repo["default_branch"] == "main",
        "publication repository mismatch",
    )
    require(
        repo["full_name"] == "raw-labs/enterprise-openclaw-bundle",
        "destination repository identity mismatch",
    )
    expected_workflow = {
        key: os.environ.get(key)
        for key in (
            "GITHUB_REPOSITORY",
            "GITHUB_SHA",
            "GITHUB_RUN_ID",
            "GITHUB_RUN_ATTEMPT",
        )
    }
    if args.build_run_id:
        require(
            re.fullmatch(r"[1-9]\d*", args.build_run_id), "invalid source build run"
        )
        prior = github_json(
            "repos/raw-labs/enterprise-openclaw-bundle/actions/runs/"
            + args.build_run_id
        )
        require(
            prior
            and prior["conclusion"] == "success"
            and prior["status"] == "completed"
            and prior["event"] == "workflow_dispatch"
            and prior["head_branch"] == "main",
            "source build is not a successful trusted main dispatch",
        )
        workflow = github_json(
            "repos/raw-labs/enterprise-openclaw-bundle/actions/workflows/"
            + str(prior["workflow_id"])
        )
        require(
            workflow and workflow["path"] == ".github/workflows/build.yml",
            "source artifacts belong to another workflow",
        )
        expected_workflow.update(
            GITHUB_SHA=prior["head_sha"],
            GITHUB_RUN_ID=str(prior["id"]),
            GITHUB_RUN_ATTEMPT=str(prior["run_attempt"]),
        )
    source = Path(args.inputs)
    out = Path(args.output).resolve()
    require(not out.exists(), "publication output exists")
    copies = {}
    receipts = {}
    for arch in ("amd64", "arm64"):
        path = source / ("native-" + arch)
        identities = {
            role: inspect_oci(
                path / role, "linux/" + arch, release["sources"]["oce"]["commit"]
            )
            for role in ROLES
        }
        receipt = load(path / "proof/native-receipt.json")
        verify_receipt(receipt, release, arch, identities)
        require(
            receipt["workflow"] == expected_workflow,
            "native receipts belong to another workflow run",
        )
        for name, hash in receipt["confinement"]["reviewedInputs"].items():
            require(
                source_files(release, args.selection)[name] == hash,
                "reviewed confinement source mismatch",
            )
        require(
            digest((path / "proof/codex-seccomp.json").read_bytes())
            == receipt["confinement"]["seccompSha256"],
            "published confinement artifact mismatch",
        )
        receipts[arch] = receipt
        copies[arch] = identities
    # Check every tag before the first write. Authentication/unknown outcomes fail closed.
    destinations = {}
    for role in ROLES:
        name = (
            release["distribution"]["namespace"].split("/", 1)[1]
            + "/"
            + ROLE_NAMES.get(role, role)
        )
        private_package(name)
        ref = "ghcr.io/raw-labs/" + name + ":" + release["id"]
        result = subprocess.run(
            [
                "skopeo",
                "inspect",
                "--authfile",
                args.authfile,
                "--raw",
                "docker://" + ref,
            ],
            capture_output=True,
            text=True,
        )
        require(
            result.returncode != 0
            and any(
                message in result.stderr.lower()
                for message in ("manifest unknown", "name unknown")
            ),
            "tag exists or absence could not be verified",
        )
        destinations[role] = (name, ref)
    out.mkdir(parents=True)
    candidate = json.loads(json.dumps(release))
    publication = {"status": "incomplete", "releaseId": release["id"], "roles": {}}
    try:
        for role, (name, ref) in destinations.items():
            directory = out / "oci" / role
            dg = assemble_index(
                directory,
                {arch: source / ("native-" + arch) / role for arch in copies},
                release["id"],
            )
            run(
                [
                    "skopeo",
                    "copy",
                    "--all",
                    "--preserve-digests",
                    "--authfile",
                    args.authfile,
                    "oci:" + str(directory) + ":" + release["id"],
                    "docker://" + ref,
                ],
                stdout=subprocess.DEVNULL,
            )
            actual = subprocess.check_output(
                [
                    "skopeo",
                    "inspect",
                    "--raw",
                    "--authfile",
                    args.authfile,
                    "docker://" + ref,
                ]
            )
            require("sha256:" + digest(actual) == dg, "published index digest changed")
            require(
                private_package(name) is not None,
                "published package access could not be verified",
            )
            candidate["images"][role].update(
                reference=ref.rsplit(":", 1)[0] + "@" + dg,
                platforms={"linux/" + arch: copies[arch][role] for arch in copies},
            )
            publication["roles"][role] = candidate["images"][role]
        for arch, receipt in receipts.items():
            path = "profiles/" + arch + "/codex-seccomp.json"
            dest = out / path
            dest.parent.mkdir(parents=True)
            shutil.copyfile(
                source / ("native-" + arch) / "proof/codex-seccomp.json", dest
            )
            candidate["payloadFiles"][path] = receipt["confinement"]["seccompSha256"]
            candidate["seccomp"]["profiles"]["linux/" + arch] = {
                "path": path,
                "sha256": candidate["payloadFiles"][path],
            }
            save(out / ("native-" + arch + "-receipt.json"), receipt)
        validate(candidate)
        candidate["qualification"]["nativeReceipts"] = {
            arch: {
                "path": "native-" + arch + "-receipt.json",
                "sha256": digest(
                    (out / ("native-" + arch + "-receipt.json")).read_bytes()
                ),
            }
            for arch in receipts
        }
        save(out / "candidate.json", candidate)
        shutil.copyfile(
            safe_path(
                Path(args.selection).parent, candidate["sources"]["oce"]["files"]
            ),
            out / candidate["sources"]["oce"]["files"],
        )
        publication["status"] = "published-private-unqualified"
    finally:
        save(out / "publication.json", publication)
    print(
        "Both native manifests published under verified private index digests; candidate remains unqualified"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("new")
    p.add_argument("--checkpoint", default="releases/source-checkpoint.json")
    p.add_argument("--id", required=True)
    p.add_argument("--output", required=True)
    p = sub.add_parser("dependencies")
    p.add_argument("--output", required=True)
    p = sub.add_parser("source")
    p.add_argument("--from-git")
    p.add_argument("--output", required=True)
    p = sub.add_parser("build")
    p.add_argument("--source", required=True)
    p.add_argument("--arch", choices=("amd64", "arm64"), required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--gha-cache", action="store_true")
    p = sub.add_parser("check")
    p.add_argument("--source", required=True)
    p.add_argument("--arch", choices=("amd64", "arm64"), required=True)
    p.add_argument("--build", required=True)
    p.add_argument("--logs", required=True)
    p = sub.add_parser("publish")
    p.add_argument("--inputs", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--authfile", required=True)
    p.add_argument("--build-run-id")
    args = parser.parse_args()
    if args.command == "new":
        new(args)
        return
    require(args.selection, "--selection is required")
    release = read_release(args.selection, ROOT)
    require(release["schemaVersion"] == 2, "stock tooling requires stock candidate")
    source_files(release, args.selection)
    if args.command == "source":
        args.release = args.selection
        prepare(args, release)
    else:
        globals()[args.command](args, release)


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
        print(f"stock: {error}", file=sys.stderr)
        sys.exit(1)
