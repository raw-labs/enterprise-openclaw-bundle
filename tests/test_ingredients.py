"""Native ingredient integrity, archive boundaries and release-bound preset wiring."""
import io
import sys
import tarfile
import unittest
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from common import digest, load
from ingredients import RegistryRedirect, package_files, plugin_selections
from release import latest_definition


class Ingredients(unittest.TestCase):
    def setUp(self):
        self.spec = load(latest_definition())
        self.plugin = next(p for p in self.spec["plugins"] if isinstance(p, dict) and p["id"] == "openclaw-connections")
        filename = self.plugin["package"].split("/")[-1] + "-" + self.plugin["version"] + ".tgz"
        self.archive = ROOT / ".work/resolved/dependencies" / filename

    def test_signed_artifact_redirect_drops_registry_authentication(self):
        request = urllib.request.Request("https://npm.pkg.github.com/download/test", headers={"Authorization": "Bearer synthetic-token"})
        handler = RegistryRedirect()
        redirected = handler.redirect_request(request, None, 302, "Found", {}, "https://pkg-npm.githubusercontent.com/test")
        self.assertIsNone(redirected.get_header("Authorization"))
        for url in ("https://other.invalid/file", "http://pkg-npm.githubusercontent.com/file"):
            with self.assertRaises(ValueError):
                handler.redirect_request(request, None, 302, "Found", {}, url)

    def test_external_pins_and_unique_ids_are_required(self):
        for changes in (
            {"version": "latest"}, {"sha256": "abc"}, {"id": "../escape"},
            {"source": {"repository": self.plugin["source"]["repository"], "commit": "main"}},
            {"source": {"repository": "https://github.com/someone/other.git", "commit": "1" * 40}},
            {"untrackedRecipe": "anything"},
        ):
            plugin = self.plugin | changes
            with self.assertRaises(ValueError):
                plugin_selections([plugin], 3)
        with self.assertRaises(ValueError):
            plugin_selections([self.plugin, self.plugin["id"]], 3)
        with self.assertRaises(ValueError):
            plugin_selections([self.plugin], 2)

    def test_real_release_package_identity_and_integrity(self):
        data = self.archive.read_bytes()
        files = package_files(data, self.plugin)
        self.assertIn("dist/index.js", files)
        self.assertIn("LICENSE", files)
        self.assertTrue(any(p.startswith("dist/control-ui/") for p in files))
        for changed in (self.plugin | {"version": "9.0.0"}, self.plugin | {"id": "other"}, self.plugin | {"sha256": "0" * 64}):
            with self.assertRaises(ValueError):
                package_files(data, changed)

    def test_archive_traversal_links_and_duplicates_rejected(self):
        for name, link, duplicate in (("package/../escape", False, False), ("package/link", True, False), ("package/same", False, True)):
            data = io.BytesIO()
            with tarfile.open(fileobj=data, mode="w:gz") as archive:
                member = tarfile.TarInfo(name)
                if link:
                    member.type = tarfile.SYMTYPE
                    member.linkname = "/etc/passwd"
                    archive.addfile(member)
                else:
                    member.size = 1
                    archive.addfile(member, io.BytesIO(b"x"))
                    if duplicate:
                        archive.addfile(member, io.BytesIO(b"x"))
            with self.assertRaises(ValueError):
                package_files(data.getvalue(), self.plugin | {"sha256": digest(data.getvalue())})

    def test_selected_presets_are_single_image_ingredients(self):
        release = load(ROOT / ".work/resolved/candidate.json")
        self.assertEqual([p["name"] for p in release["presets"]], [load(ROOT / p["path"])["name"] for p in self.spec["presets"]])
        self.assertFalse(any(p.endswith("-preset.json") for p in release["payloadFiles"]))
        for preset in release["presets"]:
            source = ROOT / ".work/resolved/source" / preset["path"].removeprefix("/app/")
            self.assertEqual(digest(source.read_bytes()), preset["sha256"])
