"""Packaging and negative input checks; synthetic OCI fixtures never qualify runtime."""

import copy
import json
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
import install as installer  # noqa: E402
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
    tap_counts,
    verify_receipt,
)


class StockInputs(unittest.TestCase):
    def setUp(self):
        self.release = read_release(SELECTION, ROOT)

    def reject(self, mutate):
        release = copy.deepcopy(self.release)
        mutate(release)
        with self.assertRaises(ValueError):
            validate(release)

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
            name = "defaults/coding-preset.json"
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
            "images": identities,
            "lanes": {
                r: {"tests": 1, "pass": 1, "fail": 0, "skipped": 0, "cancelled": 0}
                for r in identities
            },
        }
        verify_receipt(proof, self.release, "amd64", identities)
        changed = copy.deepcopy(identities)
        changed["runtime"]["digest"] = "sha256:" + "3" * 64
        with self.assertRaises(ValueError):
            verify_receipt(proof, self.release, "amd64", changed)


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
        manifest = load(self.artifact / "manifest.json")
        for path, sha in manifest.items():
            self.assertEqual(digest((self.artifact / path).read_bytes()), sha)
        self.assertFalse(
            any(
                "overlays/" in p or p.endswith("Dockerfile") or p.endswith(".log")
                for p in manifest
            )
        )
        self.assertIn("upstream/apps/controller/node_modules/tldts/LICENSE", manifest)
        self.assertNotIn("defaults/lint-values.json", manifest)
        self.assertIn(
            "upstream/apps/controller/node_modules/tldts-core/LICENSE", manifest
        )
        with tarfile.open(
            self.artifact / load(self.artifact / "release.json")["chart"]["artifact"]
        ) as chart:
            self.assertIn("openclaw-enterprise/LICENSE", chart.getnames())

    def test_delivery_tool_verifies_and_blocks_unqualified_installation(self):
        subprocess.run(
            [sys.executable, str(self.artifact / "scripts/install.py"), "verify"],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        result = subprocess.run(
            [
                sys.executable,
                str(self.artifact / "scripts/install.py"),
                "render",
                "--input",
                str(self.artifact / "examples/installations/aws.json"),
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

    def test_profiles_render_with_delivered_dependencies_and_real_chart(self):
        release = load(self.artifact / "release.json")
        chart = self.out / "chart"
        with tarfile.open(self.artifact / release["chart"]["artifact"]) as tar:
            tar.extractall(chart, filter="data")
        for profile in ("openclaw", "codex"):
            site = load(self.artifact / "examples/installations/aws.json")
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
                    str(
                        self.artifact
                        / "upstream/scripts/render-installation-profile.mjs"
                    ),
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
                    str(chart / release["chart"]["name"]),
                    "-f",
                    str(output / "values.yaml"),
                ]
            )
            self.assertIn(b"kind: Deployment", rendered)
            self.assertIn(b"kind: NetworkPolicy", rendered)

    def test_corrupt_dependency_rejected(self):
        release = load(self.artifact / "release.json")
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            (out / "tldts-7.0.18.tgz").write_bytes(b"corrupt")
            with self.assertRaises(ValueError):
                renderer_files(release, out)

    def test_mirrors_preserve_every_shipping_digest(self):
        release = load(self.artifact / "release.json")
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
        path = self.artifact / "defaults/coding-preset.json"
        original = path.read_bytes()
        try:
            path.write_bytes(original + b" ")
            result = subprocess.run(
                [sys.executable, str(self.artifact / "scripts/install.py"), "verify"],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("file integrity mismatch", result.stderr)
        finally:
            path.write_bytes(original)

    def test_architecture_selects_agent_policy_and_preserves_gateway_pool(self):
        # Bypass admission only in this renderer contract test. No qualification is recorded.
        release = load(self.artifact / "release.json")
        for role, image in release["images"].items():
            image["reference"] = "fixture.invalid/" + role + "@sha256:" + "0" * 64
        release["seccomp"]["profiles"] = {
            "linux/" + arch: {"sha256": str(index) * 64}
            for index, arch in enumerate(("amd64", "arm64"), 1)
        }
        with (
            patch.object(installer, "ROOT", self.artifact),
            patch.object(installer, "install_gate"),
        ):
            for arch in ("amd64", "arm64"):
                output = self.out / ("arch-contract-" + arch)
                args = SimpleNamespace(
                    input=self.artifact / "examples/installations/aws.json",
                    profile="codex",
                    output=output,
                    mirrors=None,
                    architecture="linux/" + arch,
                )
                installer.render(args, release)
                installation = helm_values(output / "installation.yaml")
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
            with self.assertRaisesRegex(ValueError, "select the reviewed runtime"):
                installer.render(args, release)
