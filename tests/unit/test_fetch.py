import hashlib
import io
import json
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TAG = "v1.2.3-alpha.1"


class Fetch(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.archive = self.root / "bundle.tar.gz"
        self.cache = self.root / "cache"
        self.lock = self.root / "bundle.lock.json"

    def package(self, *, extra=None):
        with tarfile.open(self.archive, "w:gz") as tar:
            for name, data, mode in (
                ("bin/prepare", b"must never be executed by fetch", 0o755),
                ("metadata/release.json", json.dumps({"id": TAG}).encode(), 0o644),
                ("metadata/manifest.json", b"{}", 0o644),
            ):
                member = tarfile.TarInfo(f"{TAG}/{name}")
                member.size, member.mode = len(data), mode
                tar.addfile(member, io.BytesIO(data))
            if extra:
                tar.addfile(extra)
        self.lock.write_text(json.dumps({
            "tag": TAG, "repository": "example/bundles", "commit": "0" * 40,
            "archive": self.archive.name, "sha256": hashlib.sha256(self.archive.read_bytes()).hexdigest(),
        }))

    def call(self, command, *extra):
        return subprocess.run(
            [sys.executable, ROOT / "delivery/fetch.py", command, "--lock", self.lock,
             "--cache", self.cache, *extra], capture_output=True, text=True,
        )

    def test_cache_is_verified_against_the_locked_archive(self):
        self.package()
        result = self.call("fetch", "--archive", self.archive)
        self.assertEqual(result.returncode, 0, result.stderr)
        bundle = Path(result.stdout.strip())
        self.assertEqual(self.call("verify").returncode, 0)
        unexpected = bundle / "bin/extra"
        unexpected.touch()
        self.assertNotEqual(self.call("verify").returncode, 0)
        unexpected.unlink()
        (bundle / "bin/prepare").write_text("changed script")
        (bundle / "metadata/manifest.json").write_text('{"changed": "manifest"}')
        self.assertIn("differs from archive", self.call("verify").stderr)

    def test_hash_and_unsafe_archive_fail_before_promotion(self):
        self.package()
        self.archive.write_bytes(self.archive.read_bytes() + b"tampered")
        self.assertIn("checksum mismatch", self.call("fetch", "--archive", self.archive).stderr)
        for extra in (tarfile.TarInfo(f"{TAG}/../escape"), tarfile.TarInfo(f"{TAG}/evil"),
                      tarfile.TarInfo(f"{TAG}/bin/prepare")):
            if extra.name.endswith("/evil"):
                extra.type, extra.linkname = tarfile.SYMTYPE, "/tmp"
            with self.subTest(entry=extra.name):
                self.package(extra=extra)
                self.assertNotEqual(self.call("fetch", "--archive", self.archive).returncode, 0)
                self.assertFalse((self.cache / TAG).exists())
