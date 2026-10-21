"""Packaging and negative input checks; synthetic OCI fixtures never qualify runtime."""

import contextlib
import copy
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "delivery"))
from common import (  # noqa: E402
    digest,
    install_gate,
    load,
    save,
    validate,
)
from stock import (  # noqa: E402
    assemble_index,
    identical_tag,
    inspect_oci,
    private_package,
    stage_archive,
    staged_tag,
    tap_counts,
    validate_docker,
    verify_baseline_runtime,
    verify_receipt,
)
from stock import (  # noqa: E402
    tests as native_tests,
)

from tests.unit.support import candidate  # noqa: E402


class StockInputs(unittest.TestCase):
    def setUp(self):
        self.release = candidate()

    def reject(self, mutate):
        release = copy.deepcopy(self.release)
        mutate(release)
        with self.assertRaises(ValueError):
            validate(release)

    def test_baseline_manifest_binds_the_native_image_without_assuming_a_config_id(
        self,
    ):
        manifest = "sha256:" + "1" * 64
        source = "2" * 40
        baseline = {
            "oceCommit": source,
            "images": {
                "runtime": {
                    "platforms": {
                        "linux/amd64": {
                            "digest": manifest,
                            "configDigest": "sha256:" + "3" * 64,
                        },
                    }
                }
            },
        }
        info = {
            "Id": manifest,
            "Descriptor": {"digest": manifest},
            "Os": "linux",
            "Architecture": "amd64",
            "Config": {
                "Labels": {
                    "org.opencontainers.image.revision": source,
                    "org.opencontainers.image.source": "https://github.com/raw-labs/enterprise-openclaw-bundle",
                }
            },
        }
        verify_baseline_runtime(info, baseline, "linux/amd64")
        for mutate in (
            lambda i: i["Descriptor"].update(digest="sha256:" + "4" * 64),
            lambda i: i.update(Architecture="arm64"),
            lambda i: i["Config"]["Labels"].update(
                {"org.opencontainers.image.revision": "5" * 40}
            ),
            lambda i: i["Config"]["Labels"].update(
                {"org.opencontainers.image.source": "https://example.invalid/other"}
            ),
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
        version = {
            side: {"Version": "29.5.3", "ApiVersion": "1.54"}
            for side in ("Client", "Server")
        }
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
not ok 2 - upstream test private-in-test-name
  ---
  error: 'private source diagnostics'
  ...
"""
        with tempfile.TemporaryDirectory() as temp:
            captured = io.StringIO()
            log = Path(temp) / "test.tap"
            with contextlib.redirect_stderr(captured), self.assertRaises(ValueError):
                native_tests(
                    [sys.executable, "-c", f"import sys; print({text!r}); sys.exit(1)"],
                    ROOT,
                    os.environ,
                    log,
                )
            self.assertIn("Native test process failed", captured.getvalue())
            self.assertNotIn("synthetic preset failure", captured.getvalue())
            self.assertNotIn("private output", captured.getvalue())
            self.assertNotIn("private source diagnostics", captured.getvalue())
            self.assertNotIn("private-in-test-name", captured.getvalue())
            self.assertIn("private source diagnostics", log.read_text())

    def test_native_promotion_requires_built_images_and_both_receipts(self):
        self.release["kind"] = "release"
        self.release["qualification"].update(
            status="native-verified", nativeReceipts={}
        )
        with self.assertRaises(ValueError):
            validate(self.release)


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
        self.release = candidate()
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
            before = {
                str(p.relative_to(source)): p.read_bytes()
                for p in source.rglob("*")
                if p.is_file()
            }
            archive = self.root / (arch + ".tar")
            tag = staged_tag("controller", self.release["id"], arch)
            reference = stage_archive(source, arch, tag, archive)
            with tarfile.open(archive) as tar:
                root = json.load(tar.extractfile("index.json"))
                descriptor = root["manifests"][0]
                index_bytes = tar.extractfile(
                    "blobs/sha256/" + descriptor["digest"].split(":")[1]
                ).read()
                self.assertEqual("sha256:" + digest(index_bytes), descriptor["digest"])
                self.assertEqual(
                    reference, tag.split(":", 1)[0] + "@" + descriptor["digest"]
                )
                self.assertEqual(
                    descriptor["annotations"]["org.opencontainers.image.ref.name"], tag
                )
                selected = json.loads(index_bytes)["manifests"][0]
                self.assertEqual(
                    selected["platform"], {"os": "linux", "architecture": arch}
                )
                self.assertEqual(
                    selected["digest"],
                    load(source / "index.json")["manifests"][0]["digest"],
                )
                for name, contents in before.items():
                    if name.startswith("blobs/"):
                        self.assertEqual(tar.extractfile(name).read(), contents)
            self.assertEqual(
                before,
                {
                    str(p.relative_to(source)): p.read_bytes()
                    for p in source.rglob("*")
                    if p.is_file()
                },
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
            **(
                {"upgradeBaseline": self.release["upgradeBaseline"]}
                if self.release.get("upgradeBaseline")
                else {}
            ),
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
                "reports": {
                    "recover": {"outcome": "missing"},
                    "reserve": {"outcome": "unavailable"},
                },
            },
        }
        for key, role in (
            ("controller", "controller"),
            ("broker", "repositoryCredentials"),
        ):
            proof["upgradeProbe"][key] = {
                "platform": "linux/amd64",
                "rootDigest": "sha256:" + "4" * 64,
                "manifestDigest": identities[role]["digest"],
                "configDigest": identities[role]["configDigest"],
                "image": staged_tag(role, self.release["id"], "amd64").split(":", 1)[0]
                + "@sha256:"
                + "4" * 64,
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
            lambda p: p["upgradeProbe"]["controller"].update(
                manifestDigest="sha256:" + "9" * 64
            ),
            lambda p: p["upgradeProbe"]["broker"].update(
                configDigest="sha256:" + "9" * 64
            ),
            lambda p: p["upgradeProbe"]["broker"].update(
                image="foreign/controller@sha256:" + "4" * 64
            ),
            lambda p: p["upgradeProbe"]["reports"]["recover"].update(outcome="unknown"),
        ):
            rejected = copy.deepcopy(proof)
            mutate(rejected)
            with self.assertRaises(ValueError):
                verify_receipt(rejected, self.release, "amd64", identities)
