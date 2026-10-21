"""Extracted-package integrity checks, including files absent from the manifest."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "delivery"))
from integrity import digest, save, verify_files, verify_package  # noqa: E402


class PackageIntegrity(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "kit"
        self.root.mkdir()
        self.files = {"INSTALL.md": digest(b"guide"), "lib/tool": digest(b"tool")}
        (self.root / "INSTALL.md").write_bytes(b"guide")
        (self.root / "lib").mkdir()
        (self.root / "lib/tool").write_bytes(b"tool")
        (self.root / "metadata").mkdir()
        self.manifest = self.root / "metadata/manifest.json"
        save(self.manifest, self.files)

    def test_complete_kit_and_cli_subset_verification(self):
        verify_package(self.root)
        # The CLI intentionally verifies its selected executable only.
        verify_files(self.root, {"lib/tool": self.files["lib/tool"]})

    def test_extra_files_and_empty_directories_are_rejected(self):
        for name in (".env", "lib/unlisted", "metadata/extra.json", "empty"):
            with self.subTest(name=name):
                path = self.root / name
                if name == "empty":
                    path.mkdir()
                else:
                    path.write_text("synthetic extra input")
                try:
                    with self.assertRaisesRegex(ValueError, "unexpected package"):
                        verify_package(self.root)
                finally:
                    path.rmdir() if path.is_dir() else path.unlink()

    def test_missing_and_changed_files_are_rejected(self):
        path = self.root / "lib/tool"
        path.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "file integrity mismatch"):
            verify_package(self.root)
        path.unlink()
        with self.assertRaisesRegex(ValueError, "file integrity mismatch"):
            verify_package(self.root)

    def test_links_and_special_files_are_rejected(self):
        for target in (
            self.root / "INSTALL.md",
            self.root / "lib",
            self.root / "missing",
        ):
            with self.subTest(target=target.name):
                extra = self.root / "link"
                extra.symlink_to(target)
                try:
                    with self.assertRaisesRegex(ValueError, "links rejected"):
                        verify_package(self.root)
                finally:
                    extra.unlink()
        extra = self.root / "pipe"
        os.mkfifo(extra)
        with self.assertRaisesRegex(ValueError, "non-regular package file"):
            verify_package(self.root)

    def test_manifest_and_its_parent_cannot_be_links(self):
        retained = self.root.parent / "retained-manifest"
        self.manifest.rename(retained)
        self.manifest.symlink_to(retained)
        with self.assertRaisesRegex(ValueError, "manifest must be a regular file"):
            verify_package(self.root)
        self.manifest.unlink()
        retained.rename(self.manifest)
        metadata = self.root / "metadata"
        external = self.root.parent / "external-metadata"
        metadata.rename(external)
        metadata.symlink_to(external, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "manifest must be a regular file"):
            verify_package(self.root)

    def test_linked_inventoried_file_and_parent_are_rejected(self):
        tool = self.root / "lib/tool"
        retained = self.root.parent / "retained-tool"
        tool.rename(retained)
        tool.symlink_to(retained)
        with self.assertRaisesRegex(ValueError, "inventory links rejected"):
            verify_package(self.root)
        tool.unlink()
        retained.rename(tool)
        library = self.root / "lib"
        external = self.root.parent / "external-library"
        library.rename(external)
        library.symlink_to(external, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "inventory links rejected"):
            verify_package(self.root)

    def test_malformed_inventories_and_path_aliases_are_rejected(self):
        for files in (
            {},
            [],
            {"metadata/manifest.json": "0" * 64},
            {"../outside": "0" * 64},
            {"/outside": "0" * 64},
            {"./INSTALL.md": self.files["INSTALL.md"]},
            {"lib//tool": self.files["lib/tool"]},
            {"INSTALL.md": None},
            {"INSTALL.md": "wrong"},
        ):
            with self.subTest(files=files):
                save(self.manifest, files)
                with self.assertRaises(ValueError):
                    verify_package(self.root)
