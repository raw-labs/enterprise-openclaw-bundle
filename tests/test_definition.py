"""Definition boundaries and genuine generated inventory; no runtime qualification fixtures."""

import copy
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from bundle import verify_source  # noqa: E402
from common import digest, install_gate, load, read_release, save  # noqa: E402
from release import (  # noqa: E402
    definition,
    latest_definition,
    pinned_file,
    preflight,
)
from stock import publish  # noqa: E402


class DefinitionInputs(unittest.TestCase):
    def setUp(self):
        self.path = latest_definition()
        self.spec = load(self.path)

    def rejected(self, mutate):
        spec = copy.deepcopy(self.spec)
        mutate(spec)
        with patch("release.load", return_value=spec):
            with self.assertRaises(ValueError):
                definition(self.path)

    def test_version_source_plugins_and_architecture_are_explicit(self):
        for mutate in (
            lambda s: s.update(version="v0.1.0"),
            lambda s: s.update(version="v0.0.0-alpha.8"),
            lambda s: s["oce"].update(commit="main"),
            lambda s: s["oce"].update(repository="ssh://unexpected/private"),
            lambda s: s.update(architectures=["linux/amd64"]),
            lambda s: s.update(plugins=["codex", "codex"]),
            lambda s: s.update(plugins=["../../outside"]),
            lambda s: s.update(qualification="qualified"),
        ):
            self.rejected(mutate)

    def test_changed_ingredient_and_path_escape_rejected(self):
        for ref in (
            {"path": "../outside", "sha256": "0" * 64},
            {"path": self.spec["codexProfile"]["path"], "sha256": "0" * 64},
        ):
            with self.assertRaises(ValueError):
                pinned_file(ref)

    def test_all_definitions_have_one_complete_selection(self):
        paths = list((ROOT / "bundles").glob("*/bundle.json"))
        self.assertTrue(paths)
        for path in paths:
            spec = definition(path)
            self.assertEqual(set(spec["build"]), {"patches", "confinement"})
            self.assertNotIn("recipe", spec)
            self.assertNotIn("installationExample", spec)

    def test_generated_inventory_covers_exact_source(self):
        selection = ROOT / ".work/resolved/candidate.json"
        release = read_release(selection, ROOT)
        verify_source(release, selection, selection.parent / "source")
        self.assertEqual(release["definitionSha256"], digest(self.path.read_bytes()))
        self.assertEqual(
            release["sources"]["oce"]["filesSha256"],
            digest((selection.parent / "source-files.json").read_bytes()),
        )

    def test_inventory_detects_changed_or_extra_export_file(self):
        selection = ROOT / ".work/resolved/candidate.json"
        release = read_release(selection, ROOT)
        source = selection.parent / "source"
        extra = source / "untracked-build-input.txt"
        try:
            extra.write_text("must not enter shipping build")
            with self.assertRaisesRegex(ValueError, "source export differs"):
                verify_source(release, selection, source)
        finally:
            extra.unlink()

    def test_unpublished_native_artifact_cannot_be_installed(self):
        release = load(ROOT / ".work/resolved/candidate.json")
        release["qualification"]["status"] = "native-verified"
        release["distribution"]["published"] = False
        with self.assertRaisesRegex(ValueError, "unpublished"):
            install_gate(release)


class ReleaseDestination(unittest.TestCase):
    def test_existing_tag_or_changed_remote_head_rejected_before_build(self):
        sha = "1" * 40
        env = {
            "GITHUB_REPOSITORY": "raw-labs/enterprise-openclaw-bundle",
            "GITHUB_REF": "refs/heads/main",
            "GITHUB_ACTOR": "publisher",
            "GITHUB_RUN_ID": "42",
        }

        def github(endpoint):
            if endpoint.endswith("actions/runs/42"):
                return {
                    "head_sha": sha,
                    "actor": {"login": "publisher"},
                    "triggering_actor": {"login": "publisher"},
                }
            if endpoint.endswith("heads/main"):
                return {"object": {"sha": sha}}
            if "/tags/" in endpoint:
                return {"object": {"sha": sha}}
            return {
                "full_name": "raw-labs/enterprise-openclaw-bundle",
                "private": True,
                "default_branch": "main",
            }

        with (
            patch.dict("os.environ", env),
            patch("release.github_json", side_effect=github),
            patch(
                "release.subprocess.check_output",
                return_value="https://github.com/raw-labs/enterprise-openclaw-bundle.git\n",
            ),
        ):
            with self.assertRaisesRegex(ValueError, "already published"):
                preflight("v0.1.0-alpha.99", sha)

    def test_native_publication_rejects_receipts_for_another_definition_or_run(self):
        # No registry write can occur before all exact OCI manifests and native receipts bind.
        selection = ROOT / ".work/resolved/candidate.json"
        release = read_release(selection, ROOT)
        with tempfile.TemporaryDirectory() as temp:
            inputs = Path(temp) / "inputs"
            proof = inputs / "native-amd64/proof"
            proof.mkdir(parents=True)
            save(
                proof / "native-receipt.json",
                {"workflow": {}, "selectionSha256": "0" * 64},
            )
            args = SimpleNamespace(
                command="assemble",
                selection=selection,
                inputs=inputs,
                output=Path(temp) / "out",
            )
            with (
                patch("stock.inspect_oci", return_value={}),
                patch("stock.verify_receipt"),
                patch("stock.assemble_index") as assemble,
            ):
                with self.assertRaises((ValueError, KeyError)):
                    publish(args, release)
                assemble.assert_not_called()
