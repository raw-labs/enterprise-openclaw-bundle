"""Release upload boundaries; synthetic assets never qualify a real release."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from common import digest, save  # noqa: E402
from release import (  # noqa: E402
    finish,
    publish_release,
    verify_installation,
    verify_release_assets,
)

VERSION = "v0.0.0-alpha.1"
ASSETS = {
    "bundle.tar.gz",
    "bundle.tar.gz.sha256",
    "bundle.json",
    "release.json",
    "publication.json",
    "source-files.json",
    "resolved.json",
    "provenance.json",
    "v0.0.0-alpha.1-native-amd64-receipt.json",
    "v0.0.0-alpha.1-native-arm64-receipt.json",
    "installation-receipt.json",
}


class ReleaseAssets(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.out = self.root / "assets"
        self.out.mkdir()
        for name in ASSETS - {"provenance.json"}:
            (self.out / name).write_text("synthetic " + name)
        self.provenance = {
            "version": VERSION,
            "published": True,
            "bundleCommit": "1" * 40,
            "workflowRun": "synthetic-run",
            "files": {
                name: digest((self.out / name).read_bytes())
                for name in ASSETS - {"provenance.json"}
            },
            "artifactSha256": digest((self.out / "bundle.tar.gz").read_bytes()),
        }
        self.write_provenance()

    def write_provenance(self):
        save(self.out / "provenance.json", self.provenance)

    def test_exact_stage_inventories_and_receipt_required(self):
        verify_release_assets(self.out, installation=True)
        with self.assertRaisesRegex(ValueError, "allowlist mismatch"):
            verify_release_assets(self.out)
        (self.out / "installation-receipt.json").unlink()
        del self.provenance["files"]["installation-receipt.json"]
        self.write_provenance()
        verify_release_assets(self.out)
        with patch("release.preflight") as preflight, patch("release.run") as run:
            with self.assertRaisesRegex(ValueError, "allowlist mismatch"):
                publish_release(SimpleNamespace(output=self.out))
            preflight.assert_not_called()
            run.assert_not_called()

    def test_extra_asset_even_with_valid_hash_never_reaches_publication(self):
        extra = self.out / ".env"
        extra.write_text("synthetic unrelated input")
        for recorded in (False, True):
            with self.subTest(recorded=recorded):
                if recorded:
                    self.provenance["files"][extra.name] = digest(extra.read_bytes())
                    self.write_provenance()
                with (
                    patch("release.preflight") as preflight,
                    patch("release.run") as run,
                ):
                    with self.assertRaisesRegex(ValueError, "allowlist mismatch"):
                        publish_release(SimpleNamespace(output=self.out))
                    preflight.assert_not_called()
                    run.assert_not_called()

    def test_missing_changed_linked_and_special_assets_are_rejected(self):
        asset = self.out / "bundle.json"
        original = asset.read_bytes()
        asset.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "handoff changed"):
            verify_release_assets(self.out, installation=True)
        asset.unlink()
        with self.assertRaisesRegex(ValueError, "allowlist mismatch"):
            verify_release_assets(self.out, installation=True)
        retained = self.root / "retained-asset"
        retained.write_bytes(original)
        asset.symlink_to(retained)
        with self.assertRaisesRegex(ValueError, "regular files"):
            verify_release_assets(self.out, installation=True)
        asset.unlink()
        os.mkfifo(asset)
        with self.assertRaisesRegex(ValueError, "regular files"):
            verify_release_assets(self.out, installation=True)
        asset.unlink()
        asset.mkdir()
        with self.assertRaisesRegex(ValueError, "regular files"):
            verify_release_assets(self.out, installation=True)

    def test_provenance_cannot_expand_or_skip_the_inventory(self):
        for name in ("../outside", "/outside", "provenance.json"):
            with self.subTest(name=name):
                self.provenance["files"][name] = "0" * 64
                self.write_provenance()
                with self.assertRaisesRegex(ValueError, "inventory mismatch"):
                    verify_release_assets(self.out, installation=True)
                del self.provenance["files"][name]
        del self.provenance["files"]["bundle.json"]
        self.write_provenance()
        with self.assertRaisesRegex(ValueError, "inventory mismatch"):
            verify_release_assets(self.out, installation=True)

    def test_version_and_provenance_link_are_rejected(self):
        self.provenance["version"] = "../other"
        self.write_provenance()
        with self.assertRaisesRegex(ValueError, "invalid release asset version"):
            verify_release_assets(self.out, installation=True)
        proof = self.out / "provenance.json"
        retained = self.root / "retained-proof"
        proof.rename(retained)
        proof.symlink_to(retained)
        with self.assertRaisesRegex(ValueError, "provenance must be a regular file"):
            verify_release_assets(self.out, installation=True)

    def test_installation_gate_rejects_strays_before_running_tools(self):
        (self.out / "installation-receipt.json").unlink()
        del self.provenance["files"]["installation-receipt.json"]
        self.write_provenance()
        (self.out / "private-log.txt").write_text("synthetic diagnostics")
        with patch("release.run") as run:
            with self.assertRaisesRegex(ValueError, "allowlist mismatch"):
                verify_installation(SimpleNamespace(output=self.out))
            run.assert_not_called()

    def test_finish_refuses_existing_output_before_reading_inputs(self):
        with self.assertRaisesRegex(ValueError, "new directory"):
            finish(SimpleNamespace(output=self.out))
        empty = self.root / "empty"
        empty.mkdir()
        with self.assertRaisesRegex(ValueError, "new directory"):
            finish(SimpleNamespace(output=empty))

    def test_publish_command_uploads_only_explicit_assets_and_external_notes(self):
        captured = []

        def capture(command):
            captured.append(command)
            if command[2] == "create":
                notes = Path(command[command.index("--notes-file") + 1])
                self.assertFalse(notes.is_relative_to(self.out))
                self.assertIn("Download", notes.read_text())

        with patch.dict(os.environ, GITHUB_SHA="1" * 40, GITHUB_RUN_ID="synthetic-run"):
            with (
                patch("release.preflight") as preflight,
                patch("release.run", side_effect=capture),
            ):
                publish_release(SimpleNamespace(output=self.out))
                preflight.assert_called_once_with(VERSION, "1" * 40)
        create, edit = captured
        assets = create[create.index("--notes-file") + 2 :]
        self.assertEqual(assets, [self.out / name for name in sorted(ASSETS)])
        self.assertIn("--draft=false", edit)
        self.assertEqual({p.name for p in self.out.iterdir()}, ASSETS)
