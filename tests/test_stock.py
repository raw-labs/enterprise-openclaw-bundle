"""Packaging and negative input checks; synthetic OCI fixtures never qualify runtime."""

import copy
import contextlib
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SELECTION = ROOT / ".work/resolved/candidate.json"
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "delivery"))
import prepare as installer  # noqa: E402
from bundle import cli_files  # noqa: E402
from release import verify_handoff_layout  # noqa: E402
from common import (  # noqa: E402
    digest,
    helm_values,
    install_gate,
    load,
    read_release,
    save,
    validate,
)
from stock import (  # noqa: E402
    assemble_index,
    identical_tag,
    inspect_oci,
    private_package,
    renderer_files,
    stage_archive,
    staged_tag,
    tap_counts,
    tests as native_tests,
    verify_baseline_runtime,
    verify_receipt,
    validate_docker,
)


class StockInputs(unittest.TestCase):
    def setUp(self):
        self.release = read_release(SELECTION, ROOT)

    def reject(self, mutate):
        release = copy.deepcopy(self.release)
        mutate(release)
        with self.assertRaises(ValueError):
            validate(release)

    def test_baseline_manifest_binds_the_native_image_without_assuming_a_config_id(self):
        manifest = "sha256:" + "1" * 64
        source = "2" * 40
        baseline = {"oceCommit": source, "images": {"runtime": {"platforms": {
            "linux/amd64": {"digest": manifest, "configDigest": "sha256:" + "3" * 64},
        }}}}
        info = {"Id": manifest, "Descriptor": {"digest": manifest}, "Os": "linux", "Architecture": "amd64",
                "Config": {"Labels": {"org.opencontainers.image.revision": source,
                                      "org.opencontainers.image.source": "https://github.com/raw-labs/enterprise-openclaw-bundle"}}}
        verify_baseline_runtime(info, baseline, "linux/amd64")
        for mutate in (
            lambda i: i["Descriptor"].update(digest="sha256:" + "4" * 64),
            lambda i: i.update(Architecture="arm64"),
            lambda i: i["Config"]["Labels"].update({"org.opencontainers.image.revision": "5" * 40}),
            lambda i: i["Config"]["Labels"].update({"org.opencontainers.image.source": "https://example.invalid/other"}),
        ):
            changed = copy.deepcopy(info)
            mutate(changed)
            with self.assertRaises(ValueError):
                verify_baseline_runtime(changed, baseline, "linux/amd64")

    def test_unbuilt_has_no_shipping_images(self):
        self.assertTrue(
            all(i["reference"] is None for i in self.release["images"].values())
        )
        with self.assertRaises(ValueError):
            install_gate(self.release)

    def test_mutable_source_and_partial_platforms_rejected(self):
        self.reject(lambda r: r["sources"]["oce"].update(commit="main"))
        self.reject(lambda r: r.update(architectures=["linux/amd64"]))

    def test_hidden_overlay_and_false_qualification_rejected(self):
        self.reject(lambda r: r["runtime"].update(overlay="overlays/codex"))
        self.reject(lambda r: r["qualification"].update(status="qualified"))

    def test_source_and_runtime_mismatches_rejected(self):
        self.reject(lambda r: r["images"]["controller"].update(oceCommit="0" * 40))
        self.reject(lambda r: r["images"]["runtime"].update(codexVersion="0.160.1"))

    def test_unexpected_destination_rejected(self):
        self.reject(
            lambda r: r["distribution"].update(namespace="someone-else/package")
        )
        self.reject(lambda r: r["distribution"].update(visibility="public"))

    def test_test_counts_reject_skips_and_empty_runs(self):
        for values in ([1, 0, 0, 1, 0], [0, 0, 0, 0, 0]):
            text = "\n".join(
                f"# {k} {v}"
                for k, v in zip(
                    ("tests", "pass", "fail", "skipped", "cancelled"),
                    values,
                    strict=True,
                )
            )
            with self.assertRaises(ValueError):
                tap_counts(text)

    def test_upgrade_docker_rejects_old_api_classic_store_and_missing_flags(self):
        version = {side: {"Version": "29.5.3", "ApiVersion": "1.54"} for side in ("Client", "Server")}
        drivers = [["driver-type", "io.containerd.snapshotter.v1"]]
        validate_docker(version, drivers, "--platform", "--platform")
        for side in ("Client", "Server"):
            old = copy.deepcopy(version)
            old[side]["ApiVersion"] = "1.48"
            with self.assertRaises(ValueError):
                validate_docker(old, drivers, "--platform", "--platform")
        for store, inspect_help, save_help in (
            ([], "--platform", "--platform"),
            (drivers, "", "--platform"),
            (drivers, "--platform", ""),
        ):
            with self.assertRaises(ValueError):
                validate_docker(version, store, inspect_help, save_help)

    def test_native_failure_diagnostics_do_not_expose_other_test_output(self):
        text = """TAP version 13
# Subtest: selected RAW presets are image-resident and accepted by OCE's real loader
not ok 1 - selected RAW presets are image-resident and accepted by OCE's real loader
  ---
  error: 'synthetic preset failure'
  ...
# private output from the next source test
# Subtest: upstream test
not ok 2 - upstream test
  ---
  error: 'private source diagnostics'
  ...
"""
        with tempfile.TemporaryDirectory() as temp:
            captured = io.StringIO()
            log = Path(temp) / "test.tap"
            with contextlib.redirect_stderr(captured), self.assertRaises(ValueError):
                native_tests([sys.executable, "-c", f"import sys; print({text!r}); sys.exit(1)"], ROOT, os.environ, log)
            self.assertIn("synthetic preset failure", captured.getvalue())
            self.assertNotIn("private output", captured.getvalue())
            self.assertNotIn("private source diagnostics", captured.getvalue())
            self.assertIn("private source diagnostics", log.read_text())

    def test_native_promotion_requires_built_images_and_both_receipts(self):
        self.release["kind"] = "release"
        self.release["qualification"].update(
            status="native-verified", nativeReceipts={}
        )
        with self.assertRaises(ValueError):
            validate(self.release)


class ReleaseSnapshots(unittest.TestCase):
    def test_archived_inputs_survive_changed_current_defaults(self):
        import shutil

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            snapshots, current = root / "snapshot", root / "current"
            shutil.copytree(
                SELECTION.parent,
                snapshots,
                ignore=shutil.ignore_patterns("source", "dependencies"),
            )
            release = read_release(snapshots / "candidate.json", ROOT)
            for name in release["payloadFiles"]:
                path = current / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("changed current input")
            self.assertEqual(
                read_release(snapshots / "candidate.json", current), release
            )

    def test_tampered_snapshot_cannot_fall_back_to_current_defaults(self):
        with tempfile.TemporaryDirectory() as temp:
            record = Path(temp) / "release.json"
            record.write_bytes(SELECTION.read_bytes())
            name = "defaults/codex-profile.json"
            tampered = record.parent / name
            tampered.parent.mkdir(parents=True)
            tampered.write_text("changed historical input\n")
            with self.assertRaisesRegex(ValueError, "payload mismatch"):
                read_release(record, ROOT)


class RegistryInputs(unittest.TestCase):
    def test_private_package_checks_documented_owner_and_optional_repository(self):
        name = "enterprise-openclaw-bundle/controller"
        package = {
            "name": name,
            "package_type": "container",
            "visibility": "private",
            "owner": {"login": "raw-labs"},
        }
        with patch("stock.github_json", return_value=package):
            self.assertEqual(private_package(name), package)
        for field, wrong in (
            ("visibility", "public"),
            ("name", "unrelated/controller"),
            ("owner", {"login": "someone-else"}),
            ("repository", {"full_name": "raw-labs/other-repository"}),
        ):
            changed = package | {field: wrong}
            with patch("stock.github_json", return_value=changed):
                with self.assertRaises(ValueError):
                    private_package(name)

    def test_retry_requires_identical_index_and_fails_on_unknown_authentication(self):
        index = '{"schemaVersion":2,"manifests":[]}\n'
        expected = "sha256:" + digest(index.encode())

        def result(code, stdout="", stderr=""):
            return subprocess.CompletedProcess([], code, stdout, stderr)

        self.assertTrue(identical_tag(result(0, index), expected))
        self.assertFalse(identical_tag(result(1, stderr="manifest unknown"), expected))
        for response in (
            result(0, "different index"),
            result(1, stderr="unauthorized"),
        ):
            with self.assertRaises(ValueError):
                identical_tag(response, expected)


class CliInputs(unittest.TestCase):
    def test_cli_rejects_another_source_missing_platform_and_changed_binary(self):
        directory = ROOT / ".work/resolved/cli"
        original = load(directory / "cli.json")
        release = read_release(SELECTION, ROOT)
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            for name in original["binaries"]:
                os.link(directory / name, out / name)
            for mutate in (
                lambda m: m.update(oceCommit="0" * 40),
                lambda m: m["binaries"].pop("occ-darwin-amd64"),
                lambda m: m["binaries"]["occ-linux-arm64"].update(sha256="0" * 64),
                lambda m: m["tests"].update(skip=1),
            ):
                metadata = copy.deepcopy(original)
                mutate(metadata)
                save(out / "cli.json", metadata)
                with self.assertRaises(ValueError):
                    cli_files(out, release)


class OciInputs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.release = read_release(SELECTION, ROOT)
        self.sha = self.release["sources"]["oce"]["commit"]

    def tearDown(self):
        self.tmp.cleanup()

    def oci(self, arch):
        root = self.root / arch
        (root / "blobs/sha256").mkdir(parents=True)

        def blob(value, media_type):
            data = json.dumps(value, sort_keys=True).encode()
            hash = digest(data)
            (root / "blobs/sha256" / hash).write_bytes(data)
            return {
                "mediaType": media_type,
                "digest": "sha256:" + hash,
                "size": len(data),
            }

        config = blob(
            {
                "os": "linux",
                "architecture": arch,
                "config": {
                    "Labels": {
                        "org.opencontainers.image.revision": self.sha,
                        "org.opencontainers.image.source": "https://github.com/raw-labs/enterprise-openclaw-bundle",
                    }
                },
            },
            "application/vnd.oci.image.config.v1+json",
        )
        manifest = blob(
            {
                "schemaVersion": 2,
                "mediaType": "application/vnd.oci.image.manifest.v1+json",
                "config": config,
                "layers": [],
            },
            "application/vnd.oci.image.manifest.v1+json",
        )
        save(root / "index.json", {"schemaVersion": 2, "manifests": [manifest]})
        return root

    def test_export_checks_architecture_source_and_blob_integrity(self):
        root = self.oci("amd64")
        inspect_oci(root, "linux/amd64", self.sha)
        for platform, sha in (("linux/arm64", self.sha), ("linux/amd64", "0" * 40)):
            with self.assertRaises(ValueError):
                inspect_oci(root, platform, sha)
        descriptor = load(root / "index.json")["manifests"][0]
        (root / "blobs/sha256" / descriptor["digest"].split(":")[1]).write_bytes(
            b"corrupt"
        )
        with self.assertRaises(ValueError):
            inspect_oci(root, "linux/amd64", self.sha)

    def test_index_preserves_both_exact_native_manifests(self):
        exports = {arch: self.oci(arch) for arch in ("amd64", "arm64")}
        identity = assemble_index(self.root / "index", exports, self.release["id"])
        data = (self.root / "index/blobs/sha256" / identity.split(":")[1]).read_bytes()
        index = json.loads(data)
        self.assertEqual(
            [d["platform"]["architecture"] for d in index["manifests"]],
            ["amd64", "arm64"],
        )
        self.assertEqual(
            [d["digest"] for d in index["manifests"]],
            [
                load(exports[a] / "index.json")["manifests"][0]["digest"]
                for a in exports
            ],
        )

    def test_staging_preserves_exact_manifest_and_original_export(self):
        for arch in ("amd64", "arm64"):
            source = self.oci(arch)
            before = {str(p.relative_to(source)): p.read_bytes() for p in source.rglob("*") if p.is_file()}
            archive = self.root / (arch + ".tar")
            tag = staged_tag("controller", self.release["id"], arch)
            reference = stage_archive(source, arch, tag, archive)
            with tarfile.open(archive) as tar:
                root = json.load(tar.extractfile("index.json"))
                descriptor = root["manifests"][0]
                index_bytes = tar.extractfile("blobs/sha256/" + descriptor["digest"].split(":")[1]).read()
                self.assertEqual("sha256:" + digest(index_bytes), descriptor["digest"])
                self.assertEqual(reference, tag.split(":", 1)[0] + "@" + descriptor["digest"])
                self.assertEqual(descriptor["annotations"]["org.opencontainers.image.ref.name"], tag)
                selected = json.loads(index_bytes)["manifests"][0]
                self.assertEqual(selected["platform"], {"os": "linux", "architecture": arch})
                self.assertEqual(selected["digest"], load(source / "index.json")["manifests"][0]["digest"])
                for name, contents in before.items():
                    if name.startswith("blobs/"):
                        self.assertEqual(tar.extractfile(name).read(), contents)
            self.assertEqual(before, {str(p.relative_to(source)): p.read_bytes() for p in source.rglob("*") if p.is_file()})

    def test_receipt_cannot_follow_a_changed_image(self):
        identities = {
            r: {"digest": "sha256:" + "1" * 64, "configDigest": "sha256:" + "2" * 64}
            for r in self.release["images"]
        }
        proof = {
            "status": "passed-native-export-checks",
            "cleanup": "completed",
            "native": True,
            "platform": "linux/amd64",
            "releaseId": self.release["id"],
            "oceCommit": self.sha,
            "openclawCommit": self.release["sources"]["openclaw"]["commit"],
            "codexVersion": self.release["runtime"]["codexVersion"],
            **({"upgradeBaseline": self.release["upgradeBaseline"]} if self.release.get("upgradeBaseline") else {}),
            "images": identities,
            "lanes": {
                r: {"tests": 1, "pass": 1, "fail": 0, "skipped": 0, "cancelled": 0}
                for r in identities
            },
            "docker": {
                "client": {"Version": "29.5.3", "ApiVersion": "1.54"},
                "server": {"Version": "29.5.3", "ApiVersion": "1.54"},
                "imageStore": "io.containerd.snapshotter.v1",
            },
            "upgradeProbe": {
                "version": 1,
                "daemonPlatform": "linux/amd64",
                "reports": {"recover": {"outcome": "missing"}, "reserve": {"outcome": "unavailable"}},
            },
        }
        for key, role in (("controller", "controller"), ("broker", "repositoryCredentials")):
            proof["upgradeProbe"][key] = {
                "platform": "linux/amd64", "rootDigest": "sha256:" + "4" * 64,
                "manifestDigest": identities[role]["digest"], "configDigest": identities[role]["configDigest"],
                "image": staged_tag(role, self.release["id"], "amd64").split(":", 1)[0] + "@sha256:" + "4" * 64,
            }
        verify_receipt(proof, self.release, "amd64", identities)
        changed = copy.deepcopy(identities)
        changed["runtime"]["digest"] = "sha256:" + "3" * 64
        with self.assertRaises(ValueError):
            verify_receipt(proof, self.release, "amd64", changed)
        for mutate in (
            lambda p: p.update(upgradeBaseline={}),
            lambda p: p.pop("upgradeProbe"),
            lambda p: p["upgradeProbe"].update(daemonPlatform="linux/arm64"),
            lambda p: p["upgradeProbe"]["controller"].update(manifestDigest="sha256:" + "9" * 64),
            lambda p: p["upgradeProbe"]["broker"].update(configDigest="sha256:" + "9" * 64),
            lambda p: p["upgradeProbe"]["broker"].update(image="foreign/controller@sha256:" + "4" * 64),
            lambda p: p["upgradeProbe"]["reports"]["recover"].update(outcome="unknown"),
        ):
            rejected = copy.deepcopy(proof)
            mutate(rejected)
            with self.assertRaises(ValueError):
                verify_receipt(rejected, self.release, "amd64", identities)


class StockArtifact(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = ROOT / ".work/resolved/source"
        cls.dependencies = ROOT / ".work/resolved/dependencies"
        if not cls.source.exists() or not cls.dependencies.exists():
            raise RuntimeError(
                "Export the stock source and verified dependency archives before packaging tests; no skips"
            )
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name)
        for name in ("one", "two"):
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/bundle.py"),
                    "--release",
                    str(SELECTION),
                    "package",
                    "--source",
                    str(cls.source),
                    "--dependencies",
                    str(cls.dependencies),
                    "--output",
                    str(cls.out / (name + ".tgz")),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
            )
        with tarfile.open(cls.out / "one.tgz") as tar:
            tar.extractall(cls.out, filter="data")
        cls.artifact = cls.out / read_release(SELECTION, ROOT)["id"]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_reproducible_customer_archive_and_inventory(self):
        self.assertEqual(
            (self.out / "one.tgz").read_bytes(), (self.out / "two.tgz").read_bytes()
        )
        manifest = load(self.artifact / "metadata/manifest.json")
        for path, sha in manifest.items():
            self.assertEqual(digest((self.artifact / path).read_bytes()), sha)
        self.assertFalse(
            any(
                "overlays/" in p or p.endswith("Dockerfile") or p.endswith(".log")
                for p in manifest
            )
        )
        self.assertIn("oce/apps/controller/node_modules/tldts/LICENSE", manifest)
        self.assertNotIn("tests/fixtures/helm-lint-values.json", manifest)
        self.assertIn("oce/apps/controller/node_modules/tldts-core/LICENSE", manifest)
        chart = (
            self.artifact
            / load(self.artifact / "metadata/release.json")["chart"]["artifact"]
        )
        self.assertTrue((chart / "LICENSE").is_file())
        self.assertFalse((self.artifact / "scripts").exists())
        image_check = self.artifact / "oce/scripts/lib/image-reference-problem.mjs"
        for image, expected in (("fixture.invalid/controller@sha256:" + "0" * 64, b""),
                                ("fixture.invalid/INVALID@sha256:" + "0" * 64, b"uppercase-repository")):
            self.assertEqual(subprocess.check_output(["node", image_check, image]), expected)
        self.assertNotIn("lib/common.py", manifest)
        self.assertFalse(
            any(
                p.startswith(
                    (
                        "oce/docs/contributing/",
                        "oce/docs/testing/",
                        "oce/docs/design/",
                    )
                )
                for p in manifest
            )
        )
        self.assertEqual(
            (self.artifact / "oce/deploy/profiles/codex.json").read_bytes(),
            (self.source / "deploy/profiles/codex.json").read_bytes(),
        )

    def test_delivery_tool_verifies_and_blocks_unqualified_installation(self):
        subprocess.run(
            [sys.executable, str(self.artifact / "bin/prepare"), "verify"],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        result = subprocess.run(
            [
                sys.executable,
                str(self.artifact / "bin/prepare"),
                "render",
                "--input",
                str(self.artifact / "examples/installations/site.json"),
                "--architecture",
                "linux/amd64",
                "--profile",
                "codex",
                "--output",
                str(self.out / "forbidden"),
            ],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("candidate cannot be installed", result.stderr)

    def test_installer_layout_links_and_commands(self):
        # Exercise the release validator on the actual unbuilt archive too.
        # Native security files are checked on the native release archive in CI.
        verify_handoff_layout(self.artifact, native=False)
        self.assertEqual(
            {p.name for p in self.artifact.iterdir()},
            {
                "AGENTS.md",
                "INSTALL.md",
                "UPDATE.md",
                "OPERATE.md",
                "bin",
                "defaults",
                "examples",
                "lib",
                "metadata",
                "notices",
                "oce",
            },
        )
        for name in ("AGENTS.md", "INSTALL.md", "UPDATE.md", "OPERATE.md"):
            document = self.artifact / name
            for target in re.findall(r"\]\(([^)]+)\)", document.read_text()):
                if "://" not in target and not target.startswith("#"):
                    self.assertTrue(
                        (document.parent / target.split("#")[0]).is_file(),
                        f"broken package document link: {name}: {target}",
                    )
        subprocess.run(
            [self.artifact / "bin/prepare", "verify"],
            cwd=self.out,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        self.assertFalse(list(self.artifact.rglob("__pycache__")))

    def test_delivered_upstream_cli_launcher_and_inventory(self):
        cli = load(self.artifact / "metadata/release.json")["operatorCli"]
        self.assertEqual(
            cli["oceCommit"], read_release(SELECTION)["sources"]["oce"]["commit"]
        )
        self.assertEqual(len(cli["binaries"]), 4)
        manifest = load(self.artifact / "metadata/manifest.json")
        for name, info in cli["binaries"].items():
            self.assertEqual(manifest["lib/occ/" + name], info["sha256"])
            self.assertTrue((self.artifact / "lib/occ" / name).stat().st_mode & 0o111)
        result = subprocess.check_output(
            [self.artifact / "bin/occ", "--version"], text=True
        )
        self.assertEqual(result.strip(), "occ " + cli["version"])
        help_text = subprocess.check_output(
            [self.artifact / "bin/occ", "--help"], text=True
        )
        self.assertIn("--service-key-file", help_text)
        # A changed delivered executable must be rejected before it can run.
        import platform

        os_name = {"Darwin": "darwin", "Linux": "linux"}[platform.system()]
        arch = {"arm64": "arm64", "aarch64": "arm64", "x86_64": "amd64"}[
            platform.machine()
        ]
        binary = self.artifact / "lib/occ" / f"occ-{os_name}-{arch}"
        original = binary.read_bytes()
        saved = binary.with_suffix(".original")
        mode = binary.stat().st_mode
        # Replace the inode: Linux can briefly retain a completed executable's
        # write lock after waitpid returns.
        binary.rename(saved)
        try:
            binary.write_bytes(original + b"changed")
            binary.chmod(mode)
            result = subprocess.run(
                [self.artifact / "bin/occ", "--version"], capture_output=True, text=True
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("file integrity mismatch", result.stderr)
        finally:
            binary.unlink(missing_ok=True)
            saved.rename(binary)

    def test_profiles_render_with_delivered_dependencies_and_real_chart(self):
        release = load(self.artifact / "metadata/release.json")
        chart = self.artifact / release["chart"]["artifact"]
        for profile in ("openclaw", "codex"):
            site = load(self.artifact / "examples/installations/site.json")
            site["controlPlane"]["controllerImage"] = (
                "fixture.invalid/controller@sha256:" + "0" * 64
            )
            site["runtime"]["image"] = "fixture.invalid/runtime@sha256:" + "0" * 64
            if profile == "codex":
                site["codex"] = {"modelDiscoveryCidrs": []}
                site["runtime"]["codexSeccompProfile"] = "openclaw/test-only.json"
            input = self.out / (profile + ".json")
            save(input, site)
            output = self.out / profile
            subprocess.run(
                [
                    "node",
                    str(self.artifact / "oce/scripts/render-installation-profile.mjs"),
                    "--profile",
                    profile,
                    "--input",
                    str(input),
                    "--out-dir",
                    str(output),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
            )
            rendered = subprocess.check_output(
                [
                    "helm",
                    "template",
                    "oce",
                    str(chart),
                    "-f",
                    str(output / "values.yaml"),
                ]
            )
            self.assertIn(b"kind: Deployment", rendered)
            self.assertIn(b"kind: NetworkPolicy", rendered)
            installation = helm_values(output / "installation.yaml")
            runtime = installation["drivers"]["compute"]["configuration"]["runtime"]
            self.assertTrue(runtime["channels"]["experimentalEmbeddedChannels"])
            self.assertTrue(runtime["gatewayOutbound"]["enabled"])
            for changes, error in (
                ({"channels": {"experimentalEmbeddedChannels": "true"}}, "must be a boolean"),
                ({"channels": {"experimentalEmbeddedChannels": True, "unknown": True}}, "not supported"),
            ):
                rejected = copy.deepcopy(site)
                rejected["runtime"].update(changes)
                save(input, rejected)
                result = subprocess.run(["node", str(self.artifact / "oce/scripts/render-installation-profile.mjs"),
                    "--profile", profile, "--input", str(input), "--out-dir", str(output)], capture_output=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(error, " ".join(load(output / "preflight.json")["errors"]))
            rejected = copy.deepcopy(site)
            rejected["gatewayOutbound"] = {"enabled": False}
            save(input, rejected)
            result = subprocess.run(["node", str(self.artifact / "oce/scripts/render-installation-profile.mjs"),
                "--profile", profile, "--input", str(input), "--out-dir", str(output)], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("requires gatewayOutbound.enabled", " ".join(load(output / "preflight.json")["errors"]))

    def test_corrupt_dependency_rejected(self):
        release = load(self.artifact / "metadata/release.json")
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            version = release["rendererDependencies"]["tldts"]["version"]
            (out / f"tldts-{version}.tgz").write_bytes(b"corrupt")
            with self.assertRaises(ValueError):
                renderer_files(release, out)

    def test_preparation_exposes_no_operational_commands(self):
        help_text = subprocess.check_output(
            [sys.executable, self.artifact / "bin/prepare", "--help"], text=True
        )
        self.assertIn("{verify,render,check}", help_text)
        for removed in ("tenant-resources", "bootstrap-read", "public-egress"):
            result = subprocess.run(
                [sys.executable, self.artifact / "bin/prepare", removed],
                capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0)

    def test_profile_selection_preserves_stock_source_and_correct_advice(self):
        site = load(self.artifact / "examples/installations/site.json")
        site["controlPlane"]["controllerImage"] = (
            "fixture.invalid/controller@sha256:" + "0" * 64
        )
        site["runtime"]["image"] = "fixture.invalid/runtime@sha256:" + "0" * 64
        site["runtime"]["codexSeccompProfile"] = "openclaw/test-only.json"
        site["codex"] = {"modelDiscoveryCidrs": []}
        path = self.out / "explicit-profile-input.json"
        save(path, site)
        for label, profile in (
            ("stock", "oce/deploy/profiles/codex.json"),
            ("curated", "defaults/codex-profile.json"),
        ):
            output = self.out / ("profile-file-" + label)
            subprocess.run(
                [
                    "node",
                    self.artifact / "oce/scripts/render-installation-profile.mjs",
                    "--profile",
                    "codex",
                    "--profile-file",
                    self.artifact / profile,
                    "--input",
                    path,
                    "--out-dir",
                    output,
                ],
                check=True,
                stdout=subprocess.DEVNULL,
            )
            configuration = helm_values(output / "installation.yaml")
            self.assertEqual(
                configuration["drivers"]["plugin"],
                load(self.artifact / profile)["installation"]["drivers"]["plugin"],
            )
            preflight = load(output / "preflight.json")
            self.assertEqual(
                any(re.search(r"Hosted.*discovery", item) for item in preflight["prerequisites"]),
                label == "stock",
            )
            self.assertTrue(
                (
                    self.artifact / "oce/deploy/helm/openclaw-enterprise/Chart.yaml"
                ).is_file()
            )

    def test_assembly_does_not_restrict_upstream_external_login(self):
        release = load(self.artifact / "metadata/release.json")
        for role, image in release["images"].items():
            image["reference"] = "fixture.invalid/" + role + "@sha256:" + "0" * 64
        site = load(self.artifact / "examples/installations/site.json")
        cp = site["controlPlane"]
        cp.pop("agentNativeAdminDomain")
        cp.pop("sharedCookieDomain")
        cp["recoveryUserId"] = "verified-admin"
        cp["oidc"] = {
            "issuer": "https://idp.example.invalid",
            "authorizationUrl": "https://idp.example.invalid/authorize",
            "tokenUrl": "https://idp.example.invalid/token",
            "jwksUrl": "https://idp.example.invalid/keys",
        }
        path = self.out / "oidc-input.json"
        save(path, site)
        output = self.out / "oidc-rendered"
        with patch.object(installer, "ROOT", self.artifact):
            installer.render(
                SimpleNamespace(
                    input=path,
                    profile="openclaw",
                    architecture="linux/amd64",
                    output=output,
                    mirrors=None,
                ),
                release,
                admit=False,
            )
        self.assertTrue(helm_values(output / "values.yaml")["auth"]["oidc"]["enabled"])

    def test_mirrors_preserve_every_shipping_digest(self):
        release = load(self.artifact / "metadata/release.json")
        for role, image in release["images"].items():
            image["reference"] = "fixture.invalid/" + role + "@sha256:" + "1" * 64
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "mirrors.json"
            mirrors = {
                role: "mirror.invalid/" + role + "@sha256:" + "1" * 64
                for role in release["images"]
            }
            save(path, mirrors)
            self.assertEqual(installer.selected_images(release, path), mirrors)
            for changed in (
                mirrors | {"runtime": "mirror.invalid/runtime:latest"},
                mirrors | {"runtime": "mirror.invalid/runtime@sha256:" + "2" * 64},
                {"runtime": mirrors["runtime"]},
            ):
                save(path, changed)
                with self.assertRaises(ValueError):
                    installer.selected_images(release, path)

    def test_delivered_file_tampering_is_detected(self):
        release = load(self.artifact / "metadata/release.json")
        path = self.artifact / "oce" / release["presets"][0]["path"].removeprefix("/app/")
        original = path.read_bytes()
        try:
            path.write_bytes(original + b" ")
            result = subprocess.run(
                [sys.executable, str(self.artifact / "bin/prepare"), "verify"],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("file integrity mismatch", result.stderr)
        finally:
            path.write_bytes(original)

    def test_architecture_selects_agent_policy_and_preserves_gateway_pool(self):
        # Bypass admission only in this renderer contract test. No qualification is recorded.
        release = load(self.artifact / "metadata/release.json")
        for role, image in release["images"].items():
            image["reference"] = "fixture.invalid/" + role + "@sha256:" + "0" * 64
        release["seccomp"]["profiles"] = {
            "linux/" + arch: {"sha256": str(index) * 64}
            for index, arch in enumerate(("amd64", "arm64"), 1)
        }
        with (
            patch.object(installer, "ROOT", self.artifact),
        ):
            for arch in ("amd64", "arm64"):
                output = self.out / ("arch-contract-" + arch)
                args = SimpleNamespace(
                    input=self.artifact / "examples/installations/site.json",
                    profile="codex",
                    output=output,
                    mirrors=None,
                    architecture="linux/" + arch,
                )
                installer.render(args, release, admit=False)
                installation = helm_values(output / "installation.yaml")
                self.assertEqual(installation["presets"]["files"], [p["path"] for p in release["presets"]])
                self.assertEqual(installation["presets"]["includeDefaults"], release["includeDefaultPresets"])
                runtime = installation["drivers"]["compute"]["configuration"]["runtime"]
                self.assertEqual(runtime["nodeSelector"]["kubernetes.io/arch"], arch)
                self.assertNotIn("kubernetes.io/arch", runtime["gatewayNodeSelector"])
                self.assertEqual(
                    runtime["codexSeccompProfile"],
                    "openclaw/codex-"
                    + release["seccomp"]["profiles"]["linux/" + arch]["sha256"]
                    + ".json",
                )
            args.architecture = None
            args.output = self.out / "missing-arch-contract"
            with self.assertRaisesRegex(ValueError, "select a released"):
                installer.render(args, release, admit=False)

    def test_site_cannot_override_selected_default_presets(self):
        release = load(self.artifact / "metadata/release.json")
        site = load(self.artifact / "examples/installations/site.json")
        site["presets"] = {"includeDefaults": not release["includeDefaultPresets"]}
        with tempfile.TemporaryDirectory() as temp, patch.object(installer, "ROOT", self.artifact):
            path = Path(temp) / "site.json"
            save(path, site)
            args = SimpleNamespace(input=path, output=Path(temp) / "rendered", mirrors=None,
                                   architecture="linux/amd64", profile="codex")
            with self.assertRaisesRegex(ValueError, "selected by the bundle"):
                installer.render(args, release, admit=False)
