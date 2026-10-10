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

from bundle import source_files, verify_source
from common import (
    ROLES,
    digest,
    load,
    read_release,
    release_file,
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


LICENSE_LAYER = b"""
FROM __UPSTREAM_TARGET__ AS bundle-notices
USER root
COPY LICENSE /usr/share/licenses/openclaw-enterprise/LICENSE
RUN chmod 0755 /usr/share/licenses /usr/share/licenses/openclaw-enterprise \\
    && chmod 0444 /usr/share/licenses/openclaw-enterprise/LICENSE
USER node
"""

INGREDIENT_LAYER = b"""
FROM __UPSTREAM_TARGET__ AS bundle-ingredients
USER root
COPY --from=bundle-plugins --chown=node:node / /app/node_modules/openclaw/dist/extensions/
COPY scripts/build-runtime-assets.mjs /tmp/bundle-inventory.mjs
COPY deploy/bundle/runtime.mjs /tmp/bundle-runtime.mjs
COPY deploy/bundle/plugins.json /tmp/bundle-plugins.json
RUN node /tmp/bundle-inventory.mjs inventory /app/node_modules/openclaw /opt/oce/runtime \\
    && node /tmp/bundle-runtime.mjs \\
    && rm /tmp/bundle-inventory.mjs /tmp/bundle-runtime.mjs /tmp/bundle-plugins.json
USER node
"""


def snapshot_inputs(release, selection, directory):
    files = {
        name: (release_file(selection, ROOT, name), expected)
        for name, expected in release["payloadFiles"].items()
    }
    definition = Path(selection).parent / "bundle.json"
    require(definition.is_file(), "missing bundle definition snapshot")
    files["bundle.json"] = (definition, release["definitionSha256"])
    files["resolved.json"] = (Path(selection), digest(Path(selection).read_bytes()))
    for name, (source, expected) in files.items():
        require(digest(source.read_bytes()) == expected, "snapshot input mismatch")
        target = safe_path(directory, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        require(
            not target.exists() or target.read_bytes() == source.read_bytes(),
            "snapshot would replace existing inputs",
        )
        if target != source.resolve():
            shutil.copyfile(source, target)


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
        prefix = "oce/apps/controller/node_modules/" + name + "/"
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


def validate_docker(version, drivers, inspect_help, save_help):
    for side in ("Client", "Server"):
        api = version[side]["ApiVersion"]
        require(
            re.fullmatch(r"\d+\.\d+", api) and tuple(map(int, api.split("."))) >= (1, 49),
            "OCE's image probe requires Docker CLI and Engine API 1.49+ (28.1+)",
        )
    require(
        ["driver-type", "io.containerd.snapshotter.v1"] in drivers,
        "OCE's image probe requires Docker's containerd image store",
    )
    require(
        "--platform" in inspect_help and "--platform" in save_help,
        "OCE's image probe requires platform-specific image inspect and save",
    )
    return {
        side.lower(): {key: version[side][key] for key in ("Version", "ApiVersion")}
        for side in ("Client", "Server")
    } | {"imageStore": "io.containerd.snapshotter.v1"}


def docker_preflight():
    def output(args):
        return subprocess.check_output(["docker", *args], text=True)

    return validate_docker(
        json.loads(output(["version", "--format", "{{json .}}"])),
        json.loads(output(["info", "--format", "{{json .DriverStatus}}"])),
        output(["image", "inspect", "--help"]),
        output(["image", "save", "--help"]),
    )


def staged_tag(role, version, arch):
    return f"localhost/bundle-{ROLE_NAMES.get(role, role)}:{version}-{arch}"


def native_index(descriptor, arch):
    manifest = {key: descriptor[key] for key in ("mediaType", "digest", "size")}
    manifest["platform"] = {"os": "linux", "architecture": arch}
    index = {
        "schemaVersion": 2,
        "mediaType": "application/vnd.oci.image.index.v1+json",
        "manifests": [manifest],
    }
    return (json.dumps(index, sort_keys=True, separators=(",", ":")) + "\n").encode()


def stage_archive(directory, arch, tag, output):
    """Preserve the native manifest under an OCI index, without a registry upload."""
    descriptor = load(directory / "index.json")["manifests"][0]
    data = native_index(descriptor, arch)
    root_digest = "sha256:" + digest(data)
    root = {
        "schemaVersion": 2,
        "manifests": [{
            "mediaType": "application/vnd.oci.image.index.v1+json",
            "digest": root_digest,
            "size": len(data),
            "annotations": {"org.opencontainers.image.ref.name": tag},
        }],
    }
    with tarfile.open(output, "w") as archive:
        for name, content in (
            ("index.json", json.dumps(root).encode()),
            ("blobs/sha256/" + root_digest.split(":")[1], data),
            ("oci-layout", b'{"imageLayoutVersion":"1.0.0"}\n'),
        ):
            entry = tarfile.TarInfo(name)
            entry.size = len(content)
            archive.addfile(entry, io.BytesIO(content))
        for blob in sorted((directory / "blobs/sha256").iterdir()):
            require(blob.is_file() and not blob.is_symlink(), "invalid OCI blob file")
            archive.add(blob, arcname="blobs/sha256/" + blob.name)
    return tag.split(":", 1)[0] + "@" + root_digest


def verify_upgrade_probe(proof, release, arch, identities):
    platform = "linux/" + arch
    require(
        proof["version"] == 1 and proof["daemonPlatform"] == platform,
        "upgrade probe platform mismatch",
    )
    for key, role in (("controller", "controller"), ("broker", "repositoryCredentials")):
        identity = proof[key]
        require(
            identity["platform"] == platform
            and identity["manifestDigest"] == identities[role]["digest"]
            and identity["configDigest"] == identities[role]["configDigest"]
            and bool(DIGEST.fullmatch(identity["rootDigest"]))
            and identity["image"] == staged_tag(role, release["id"], arch).split(":", 1)[0]
            + "@" + identity["rootDigest"],
            "upgrade probe image mismatch",
        )
    require(
        proof["reports"]["recover"]["outcome"] == "missing"
        and proof["reports"]["reserve"]["outcome"] == "unavailable",
        "upgrade probe protocol mismatch",
    )


def verify_baseline_runtime(info, baseline, platform):
    # The manifest binds its config and layers. Docker's image ID is not a config digest.
    require(
        info["Descriptor"]["digest"] == baseline["images"]["runtime"]["platforms"][platform]["digest"]
        and info["Os"] + "/" + info["Architecture"] == platform
        and info["Config"]["Labels"]["org.opencontainers.image.revision"] == baseline["oceCommit"]
        and info["Config"]["Labels"]["org.opencontainers.image.source"]
        == "https://github.com/raw-labs/enterprise-openclaw-bundle",
        "upgrade baseline runtime identity mismatch",
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
        fragment = LICENSE_LAYER
        require(
            digest(fragment) == release["build"]["noticeLayerSha256"],
            "license build code changed",
        )
        # Append recorded native ingredients and required notices to the selected recipe.
        with tempfile.TemporaryDirectory() as temporary:
            dockerfile = Path(temporary) / "Dockerfile"
            upstream_target = recipe["target"]
            ingredients = b""
            if role == "runtime" and release.get("pluginPackages"):
                require(digest(INGREDIENT_LAYER) == release["build"]["ingredientLayerSha256"], "ingredient build code changed")
                cmd.extend(["--build-context", f"bundle-plugins={Path(args.source).resolve() / 'deploy/bundle/plugins'}"])
                ingredients = INGREDIENT_LAYER.replace(b"__UPSTREAM_TARGET__", upstream_target.encode())
                upstream_target = "bundle-ingredients"
            dockerfile.write_bytes(
                (Path(args.source) / recipe["dockerfile"]).read_bytes()
                + ingredients
                + fragment.replace(b"__UPSTREAM_TARGET__", upstream_target.encode())
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
    output = log.read_text()
    if result.returncode:
        # Only these factory tests use fresh state and fixed, synthetic credentials.
        # Other source-test diagnostics remain in the private log.
        public_tests = {
            "selected RAW presets are image-resident and accepted by OCE's real loader",
            "packaged native extensions and their inventory match the selected release",
            "Connections loads in the native Gateway and retains its database across Kubernetes Pod replacement",
        }
        for block in re.split(r"(?m)(?=^# Subtest: )", output):
            failure = re.match(r"^# Subtest: ([^\n]+)\nnot ok [^\n]+\n  ---\n.*?\n  \.\.\.(?:\n|$)", block, re.DOTALL)
            if failure and failure[1] in public_tests:
                print(failure[0][:16384], file=sys.stderr)
    require(result.returncode == 0, f"native lane failed; private diagnostics: {log}")
    return tap_counts(output)


def check(args, release):
    native_arch(args.arch)
    require(os.getuid() == 1000 or os.environ.get("GITHUB_ACTIONS") == "true",
            "run as UID 1000; CI may use its prepared UID 1000 probe user")
    toolchain = docker_preflight()
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
    staged = {}
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
        "selectionSha256": digest(Path(args.selection).read_bytes()),
        "definitionSha256": release["definitionSha256"],
        "lanes": {},
        "docker": toolchain,
        "scope": "native shipping export tests; no provider workflow or customer installation qualification",
    }
    env = dict(os.environ)
    try:
        for role in ROLES:
            identity = inspect_oci(out / role, record["platform"], record["oceCommit"])
            require(identity == record["images"][role], "built OCI identity changed")
            tag = staged_tag(role, release["id"], args.arch)
            existing = subprocess.run(
                ["docker", "image", "inspect", tag],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            require(existing.returncode != 0, "local export tag already exists")
            # Claim cleanup before import: Docker can load the tag before exiting with an error.
            tags.append(tag)
            with tempfile.TemporaryDirectory() as temporary:
                archive = Path(temporary) / "image.tar"
                staged[role] = stage_archive(out / role, args.arch, tag, archive)
                run(["docker", "image", "load", "--input", archive], stdout=subprocess.DEVNULL)
            info = json.loads(
                subprocess.check_output(["docker", "image", "inspect", tag])
            )[0]
            selected = json.loads(subprocess.check_output(
                ["docker", "image", "inspect", "--platform", record["platform"], tag]
            ))[0]
            require(
                info["Descriptor"]["digest"] == staged[role].rsplit("@", 1)[1]
                and selected["Descriptor"]["digest"] == identity["digest"]
                and selected["Os"] + "/" + selected["Architecture"] == record["platform"],
                "loaded image differs from tested export",
            )
            images[role] = info["Id"]
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
        log = logs / "upgrade-probe.json"
        command = ["node", source / "scripts/upgrade-repository-image-probe.mjs",
                   staged["controller"], staged["repositoryCredentials"], record["platform"]]
        if os.getuid() != 1000:
            command = ["sudo", "--user=#1000", "--", "env", "PATH=" + env["PATH"], *command]
        with log.open("w") as file:
            os.chmod(log, 0o600)
            result = subprocess.run(
                command,
                cwd=source, env=env, stdout=file, stderr=subprocess.STDOUT, timeout=360,
            )
        require(result.returncode == 0, f"OCE's image probe failed; private diagnostics: {log}")
        proof = load(log)
        verify_upgrade_probe(proof, release, args.arch, record["images"])
        receipt["upgradeProbe"] = {key: proof[key] for key in (
            "version", "daemonPlatform", "controller", "broker", "reports"
        )}
        node = ["node", "--test", "--test-concurrency=1", "--test-reporter=tap"]
        baseline = release.get("upgradeBaseline")
        if baseline:
            previous = baseline["images"]["runtime"]
            # Import only this target's immutable manifest, as k3d needs a complete local image.
            reference = (previous["reference"].split("@", 1)[0] + "@"
                         + previous["platforms"][record["platform"]]["digest"])
            existing = subprocess.run(["docker", "image", "inspect", reference],
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if existing.returncode != 0:
                tags.append(reference)
            run(["docker", "pull", "--platform", record["platform"], reference], stdout=subprocess.DEVNULL)
            info = json.loads(subprocess.check_output([
                "docker", "image", "inspect", "--platform", record["platform"], reference]))[0]
            verify_baseline_runtime(info, baseline, record["platform"])
            env["BUNDLE_UPGRADE_RUNTIME_IMAGE"] = reference
            receipt["upgradeBaseline"] = baseline
        receipt["lanes"]["controller"] = tests(
            [*node, "tests/integration/production-image-startup.test.mjs", ROOT / "tests/native_presets.mjs"],
            source,
            dict(env, OCC_TEST_PRODUCTION_IMAGE=images["controller"], BUNDLE_TEST_SELECTION=str(Path(args.selection).resolve())),
            logs / "controller.tap",
        )
        connections = tests(
            [*node, ROOT / "tests/native_connections.mjs"],
            source,
            dict(env, OCC_TEST_RUNTIME_IMAGE=images["runtime"],
                 BUNDLE_TEST_SELECTION=str(Path(args.selection).resolve())),
            logs / "connections.tap",
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
            dict(env, BUNDLE_TEST_SELECTION=str(Path(args.selection).resolve())),
            logs / "runtime.tap",
        )
        for key, value in connections.items():
            receipt["lanes"]["runtime"][key] += value
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
            p.name: digest(p.read_bytes()) for p in logs.iterdir() if p.is_file()
        }
        save(report / "native-receipt.json", receipt)
    print("Native export checks passed without skips")


def verify_receipt(receipt, release, arch, identities):
    require(receipt.get("upgradeBaseline") == release.get("upgradeBaseline"),
            "native upgrade baseline mismatch")
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
    require("upgradeProbe" in receipt, "OCE's native image probe proof is required")
    verify_upgrade_probe(receipt["upgradeProbe"], release, arch, identities)
    docker = receipt["docker"]
    validate_docker(
        {side: docker[side.lower()] for side in ("Client", "Server")},
        [["driver-type", docker["imageStore"]]], "--platform", "--platform",
    )
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
            and package["name"] == name
            and package["package_type"] == "container"
            and package["owner"]["login"] == "raw-labs",
            "package visibility or namespace ownership mismatch",
        )
        # The documented Packages REST response need not contain a repository.
        # Exact OCI source labels and trusted native receipts bind the repository.
        linked = package.get("repository")
        if linked is not None:
            require(
                linked["full_name"] == "raw-labs/enterprise-openclaw-bundle",
                "package belongs to another repository",
            )
    return package


def identical_tag(result, expected):
    if result.returncode == 0:
        require(
            "sha256:" + digest(result.stdout.encode()) == expected,
            "existing tag differs from the exact tested index; refusing overwrite",
        )
        return True
    require(
        any(
            message in result.stderr.lower()
            for message in ("manifest unknown", "name unknown")
        ),
        "tag absence could not be verified",
    )
    return False


def publish(args, release):
    require(
        release["kind"] == "candidate", "publication requires an unqualified candidate"
    )
    publishing = args.command == "publish"
    if publishing:
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
            all(
                receipt["workflow"][key] == value
                for key, value in expected_workflow.items()
                if key != "GITHUB_RUN_ATTEMPT"
            )
            and re.fullmatch(r"[1-9]\d*", receipt["workflow"]["GITHUB_RUN_ATTEMPT"])
            and receipt["selectionSha256"] == digest(Path(args.selection).read_bytes())
            and receipt["definitionSha256"] == release["definitionSha256"],
            "native receipts belong to another workflow or definition",
        )
        require(
            set(receipt["confinement"]["reviewedInputs"])
            == {
                "scripts/lib/codex-seccomp-profile.mjs",
                ".github/actions/run-ci-lane/codex-sandbox.apparmor",
            },
            "native confinement input inventory incomplete",
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
    # Prepare every index and check every tag before the first registry write.
    # An identical existing tag is verified and reused, never overwritten.
    out.mkdir(parents=True)
    destinations = {}
    for role in ROLES:
        directory = out / "oci" / role
        dg = assemble_index(
            directory,
            {arch: source / ("native-" + arch) / role for arch in copies},
            release["id"],
        )
        name = (
            release["distribution"]["namespace"].split("/", 1)[1]
            + "/"
            + ROLE_NAMES.get(role, role)
        )
        if publishing:
            private_package(name)
        ref = "ghcr.io/raw-labs/" + name + ":" + release["id"]
        exists = False
        if publishing:
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
            exists = identical_tag(result, dg)
            if exists:
                require(
                    private_package(name) is not None,
                    "existing package is unverifiable",
                )
        destinations[role] = (name, ref, dg, exists)
    candidate = json.loads(json.dumps(release))
    publication = {"status": "incomplete", "releaseId": release["id"], "roles": {}}
    try:
        for role, (name, ref, dg, exists) in destinations.items():
            directory = out / "oci" / role
            if publishing:
                if not exists:
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
                require(
                    "sha256:" + digest(actual) == dg, "published index digest changed"
                )
                require(
                    private_package(name) is not None,
                    "published package access could not be verified",
                )
            candidate["images"][role].update(
                reference=ref.rsplit(":", 1)[0] + "@" + dg,
                platforms={"linux/" + arch: copies[arch][role] for arch in copies},
            )
            publication["roles"][role] = candidate["images"][role]
            save(out / "publication.json", publication)
        for arch, receipt in receipts.items():
            path = "security/seccomp/" + arch + "/codex-seccomp.json"
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
            save(out / (release["id"] + "-native-" + arch + "-receipt.json"), receipt)
        validate(candidate)
        candidate["qualification"]["nativeReceipts"] = {
            arch: {
                "path": release["id"] + "-native-" + arch + "-receipt.json",
                "sha256": digest(
                    (
                        out / (release["id"] + "-native-" + arch + "-receipt.json")
                    ).read_bytes()
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
        snapshot_inputs(release, args.selection, out)
        publication["status"] = (
            "published-private-unqualified" if publishing else "checked-unpublished"
        )
    finally:
        save(out / "publication.json", publication)
    print(
        "Both native manifests verified and assembled; publication=" + str(publishing)
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("docker-preflight")
    p = sub.add_parser("dependencies")
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
    for command in ("publish", "assemble"):
        p = sub.add_parser(command)
        p.add_argument("--inputs", required=True)
        p.add_argument("--output", required=True)
        if command == "publish":
            p.add_argument("--authfile", required=True)
    args = parser.parse_args()
    if args.command == "docker-preflight":
        print(json.dumps(docker_preflight(), sort_keys=True))
        return
    require(args.selection, "--selection is required")
    release = read_release(args.selection, ROOT)
    require(release["schemaVersion"] == 2, "stock tooling requires stock candidate")
    source_files(release, args.selection)
    (publish if args.command == "assemble" else globals()[args.command])(args, release)


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
