"""Definition boundaries and genuine generated inventory; no runtime qualification fixtures."""

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SELECTION = Path(
    os.environ.get("BUNDLE_TEST_SELECTION", ROOT / ".work/resolved/candidate.json")
).resolve()
sys.path.insert(0, str(ROOT / "scripts"))
from bundle import verify_source  # noqa: E402
from common import (  # noqa: E402
    digest,
    install_gate,
    load,
    read_release,
)


class DefinitionInputs(unittest.TestCase):
    def setUp(self):
        self.path = SELECTION.parent / "bundle.json"

    def test_generated_inventory_covers_exact_source(self):
        selection = SELECTION
        release = read_release(selection, ROOT)
        verify_source(release, selection, selection.parent / "source")
        self.assertEqual(release["definitionSha256"], digest(self.path.read_bytes()))
        self.assertEqual(
            release["sources"]["oce"]["filesSha256"],
            digest((selection.parent / "source-files.json").read_bytes()),
        )

    def test_inventory_detects_changed_or_extra_export_file(self):
        selection = SELECTION
        release = read_release(selection, ROOT)
        source = selection.parent / "source"
        extra = source / "untracked-build-input.txt"
        try:
            extra.write_text("must not enter shipping build")
            with self.assertRaisesRegex(ValueError, "source export differs"):
                verify_source(release, selection, source)
        finally:
            extra.unlink()

    def test_codex_recipe_requires_the_entire_selected_version(self):
        selection = SELECTION
        release = read_release(selection, ROOT)
        # A recipe suffix must not be mistaken for the shorter selected prerelease.
        source = selection.parent / "source"
        release["runtime"]["codexVersion"] += "0"
        with self.assertRaisesRegex(ValueError, "stock Codex/source mismatch"):
            verify_source(release, selection, source)

    def test_unpublished_native_artifact_cannot_be_installed(self):
        release = load(SELECTION)
        release["qualification"]["status"] = "native-verified"
        release["distribution"]["published"] = False
        with self.assertRaisesRegex(ValueError, "unpublished"):
            install_gate(release)
