"""Licensing build contexts must not include changed or unrelated files."""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from bundle import BUNDLE_LICENSE_FILES  # noqa: E402
from common import digest  # noqa: E402
from stock import license_context  # noqa: E402


class LicenseContext(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.selection = self.root / "candidate.json"
        self.directory = self.root / "notices"
        self.release = {"payloadFiles": {}}
        for name in BUNDLE_LICENSE_FILES:
            data = (ROOT / name).read_bytes()
            path = self.directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            self.release["payloadFiles"]["notices/" + name] = digest(data)

    def test_modified_missing_extra_and_linked_notices_are_rejected(self):
        self.assertEqual(
            license_context(self.release, self.selection), self.directory.resolve()
        )
        path = self.directory / "LICENSE"
        original = path.read_bytes()
        path.write_bytes(original + b"changed")
        with self.assertRaisesRegex(ValueError, "file integrity mismatch"):
            license_context(self.release, self.selection)
        path.unlink()
        with self.assertRaisesRegex(ValueError, "inventory mismatch"):
            license_context(self.release, self.selection)
        path.write_bytes(original)
        extra = self.directory / "unrelated.env"
        extra.write_text("synthetic unrelated build input")
        with self.assertRaisesRegex(ValueError, "inventory mismatch"):
            license_context(self.release, self.selection)
        extra.unlink()
        retained = self.root / "original-license"
        path.rename(retained)
        path.symlink_to(retained)
        with self.assertRaisesRegex(ValueError, "links rejected"):
            license_context(self.release, self.selection)
