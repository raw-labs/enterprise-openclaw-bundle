"""Packaging and negative input checks; synthetic OCI fixtures never qualify runtime."""

import copy
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

ROOT = Path(__file__).resolve().parents[2]
SELECTION = Path(
    os.environ.get("BUNDLE_TEST_SELECTION", ROOT / ".work/resolved/candidate.json")
).resolve()
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "delivery"))
import prepare as installer  # noqa: E402
from bundle import BUNDLE_LICENSE_FILES, cli_files, preparation_tool  # noqa: E402
from common import (  # noqa: E402
    digest,
    helm_values,
    load,
    read_release,
    save,
)
from release import verify_handoff_layout  # noqa: E402
from stock import (  # noqa: E402
    renderer_files,
)


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


class CliInputs(unittest.TestCase):
    def test_cli_rejects_another_source_missing_platform_and_changed_binary(self):
        directory = SELECTION.parent / "cli"
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


class StockArtifact(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SELECTION.parent / "source"
        cls.dependencies = SELECTION.parent / "dependencies"
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
        release = read_release(SELECTION, ROOT)
        for name in BUNDLE_LICENSE_FILES:
            self.assertEqual(
                (self.artifact / "notices" / name).read_bytes(),
                (ROOT / name).read_bytes(),
            )
            self.assertEqual(
                manifest["notices/" + name], release["payloadFiles"]["notices/" + name]
            )
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
        upstream_license = (self.source / "LICENSE").read_bytes()
        self.assertEqual((chart / "LICENSE").read_bytes(), upstream_license)
        self.assertEqual(
            (self.artifact / "notices/OCE-LICENSE").read_bytes(), upstream_license
        )
        self.assertEqual((ROOT / "LICENSES/OCE-MIT.txt").read_bytes(), upstream_license)
        for name, dependency in release["rendererDependencies"].items():
            with tarfile.open(
                self.dependencies / f"{name}-{dependency['version']}.tgz"
            ) as archive:
                original = archive.extractfile("package/LICENSE").read()
            self.assertEqual(
                (
                    self.artifact
                    / "oce/apps/controller/node_modules"
                    / name
                    / "LICENSE"
                ).read_bytes(),
                original,
            )
        self.assertFalse((self.artifact / "scripts").exists())
        image_check = self.artifact / "oce/scripts/lib/image-reference-problem.mjs"
        for image, expected in (
            ("fixture.invalid/controller@sha256:" + "0" * 64, b""),
            ("fixture.invalid/INVALID@sha256:" + "0" * 64, b"uppercase-repository"),
        ):
            self.assertEqual(
                subprocess.check_output(["node", image_check, image]), expected
            )
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
                "SUPPORT.md",
                "SECURITY.md",
                "bin",
                "defaults",
                "examples",
                "lib",
                "metadata",
                "notices",
                "oce",
            },
        )
        for name in ("AGENTS.md", "INSTALL.md", "UPDATE.md", "OPERATE.md", "SUPPORT.md", "SECURITY.md"):
            document = self.artifact / name
            contents = document.read_text()
            self.assertNotIn("openclaw-enterprise/blob/main/", contents)
            for target in re.findall(r"\]\(([^)]+)\)", document.read_text()):
                if "://" not in target and not target.startswith("#"):
                    self.assertTrue(
                        (document.parent / target.split("#")[0]).is_file(),
                        f"broken package document link: {name}: {target}",
                    )
        plugin = next(
            p
            for p in read_release(SELECTION)["pluginPackages"]
            if p["id"] == "openclaw-connections"
        )
        self.assertIn(
            plugin["source"]["commit"] + "/README.md#install-and-configure",
            (self.artifact / "OPERATE.md").read_text(),
        )
        subprocess.run(
            [self.artifact / "bin/prepare", "verify"],
            cwd=self.out,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        self.assertFalse(list(self.artifact.rglob("__pycache__")))

    def test_delivered_commands_reject_extra_files_before_preparation(self):
        extra = self.artifact / "metadata/unlisted.json"
        extra.write_text("synthetic extra package file")
        destination = self.out / "must-not-render"
        try:
            for args in (
                ["verify"],
                ["check", "--directory", self.out / "missing-render"],
                ["render", "--input", self.artifact / "examples/installations/site.json",
                 "--profile", "codex", "--architecture", "linux/amd64",
                 "--output", destination],
            ):
                with self.subTest(command=args[0]):
                    result = subprocess.run(
                        [self.artifact / "bin/prepare", *args],
                        capture_output=True, text=True,
                    )
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("unexpected package file", result.stderr)
            self.assertFalse(destination.exists())
        finally:
            extra.unlink()

    def test_in_process_renderer_keeps_the_package_inventory_clean(self):
        prior = sys.dont_write_bytecode
        try:
            sys.dont_write_bytecode = False
            renderer = preparation_tool(self.artifact)
            self.assertEqual(renderer.ROOT, self.artifact.resolve())
            self.assertFalse(sys.dont_write_bytecode)
            self.assertFalse(list(self.artifact.rglob("__pycache__")))
            subprocess.run([self.artifact / "bin/prepare", "verify"], check=True,
                           stdout=subprocess.DEVNULL)
        finally:
            sys.dont_write_bytecode = prior

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
            self.assertFalse(runtime["channels"]["experimentalEmbeddedChannels"])
            self.assertTrue(runtime["gatewayOutbound"]["enabled"])
            for changes, error in (
                (
                    {"channels": {"experimentalEmbeddedChannels": "true"}},
                    "must be a boolean",
                ),
                (
                    {
                        "channels": {
                            "experimentalEmbeddedChannels": True,
                            "unknown": True,
                        }
                    },
                    "not supported",
                ),
            ):
                rejected = copy.deepcopy(site)
                rejected.update(changes)
                save(input, rejected)
                result = subprocess.run(
                    [
                        "node",
                        str(
                            self.artifact
                            / "oce/scripts/render-installation-profile.mjs"
                        ),
                        "--profile",
                        profile,
                        "--input",
                        str(input),
                        "--out-dir",
                        str(output),
                    ],
                    capture_output=True,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(
                    error, " ".join(load(output / "preflight.json")["errors"])
                )
            rejected = copy.deepcopy(site)
            rejected["gatewayOutbound"] = {"enabled": False}
            rejected["channels"]["experimentalEmbeddedChannels"] = True
            save(input, rejected)
            result = subprocess.run(
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
                capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "requires gatewayOutbound.enabled",
                " ".join(load(output / "preflight.json")["errors"]),
            )

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
                any(
                    re.search(r"Hosted.*discovery", item)
                    for item in preflight["prerequisites"]
                ),
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
        path = (
            self.artifact / "oce" / release["presets"][0]["path"].removeprefix("/app/")
        )
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
                self.assertEqual(
                    installation["presets"]["files"],
                    [p["path"] for p in release["presets"]],
                )
                self.assertEqual(
                    installation["presets"]["includeDefaults"],
                    release["includeDefaultPresets"],
                )
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
        with (
            tempfile.TemporaryDirectory() as temp,
            patch.object(installer, "ROOT", self.artifact),
        ):
            path = Path(temp) / "site.json"
            save(path, site)
            args = SimpleNamespace(
                input=path,
                output=Path(temp) / "rendered",
                mirrors=None,
                architecture="linux/amd64",
                profile="codex",
            )
            with self.assertRaisesRegex(ValueError, "selected by the bundle"):
                installer.render(args, release, admit=False)
