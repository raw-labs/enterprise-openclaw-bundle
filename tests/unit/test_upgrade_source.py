"""Archive upgrades retain source identity, complete inventory and chart isolation."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "delivery"))
from integrity import digest, save  # noqa: E402
from upgrade_source import verify_upgrade_source  # noqa: E402


class ArchiveUpgradeSource(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "kit"
        self.chart = self.root / "oce/deploy/helm/openclaw-enterprise"
        self.chart.mkdir(parents=True)
        (self.chart / "Chart.yaml").write_text("name: test\n")
        (self.root / "metadata").mkdir()
        self.revision = "a" * 40
        save(self.root / "metadata/release.json", {"sources": {"oce": {"commit": self.revision}}})
        save(self.root / "metadata/manifest.json", {
            p.relative_to(self.root).as_posix(): digest(p.read_bytes())
            for p in self.root.rglob("*") if p.is_file()
        })
        previous = Path.cwd()
        os.chdir(self.root / "oce")
        self.addCleanup(os.chdir, previous)

    def test_archive_without_git_and_external_outputs(self):
        checksum = verify_upgrade_source(self.root, self.revision, [self.root.parent / "evidence"])
        self.assertEqual(len(checksum), 64)
        self.assertFalse((self.root / "oce/.git").exists())

    def test_wrong_revision_rejected(self):
        with self.assertRaisesRegex(ValueError, "source revision mismatch"):
            verify_upgrade_source(self.root, "b" * 40, [])

    def test_modified_and_extra_chart_files_rejected(self):
        (self.chart / "Chart.yaml").write_text("changed")
        with self.assertRaisesRegex(ValueError, "integrity mismatch"):
            verify_upgrade_source(self.root, self.revision, [])

    def test_extra_file_rejected(self):
        (self.chart / "extra").write_text("extra")
        with self.assertRaisesRegex(ValueError, "unexpected package file"):
            verify_upgrade_source(self.root, self.revision, [])

    def test_outputs_inside_chart_rejected_including_symlink_alias(self):
        alias = self.root.parent / "alias"
        alias.symlink_to(self.chart, target_is_directory=True)
        for output in (self.chart / "new/evidence", alias / "new/evidence", self.chart / "Chart.yaml"):
            with self.subTest(output=output), self.assertRaisesRegex(ValueError, "outside the packaged Helm chart"):
                verify_upgrade_source(self.root, self.revision, [output])

    def test_wrong_working_directory_rejected(self):
        os.chdir(self.root)
        with self.assertRaisesRegex(ValueError, "candidate oce directory"):
            verify_upgrade_source(self.root, self.revision, [])
