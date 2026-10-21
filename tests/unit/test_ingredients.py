"""Native ingredient integrity, archive boundaries and release-bound preset wiring."""

import io
import sys
import tarfile
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from common import digest, load  # noqa: E402
from ingredients import (  # noqa: E402
    RegistryRedirect,
    ReleaseRedirect,
    download_package,
    package_files,
    plugin_selections,
)
from release import latest_definition  # noqa: E402


class Ingredients(unittest.TestCase):
    def setUp(self):
        self.spec = load(latest_definition())
        self.plugin = next(
            p
            for p in self.spec["plugins"]
            if isinstance(p, dict) and p["id"] == "openclaw-connections"
        )

    def test_signed_artifact_redirect_drops_registry_authentication(self):
        request = urllib.request.Request(
            "https://npm.pkg.github.com/download/test",
            headers={"Authorization": "Bearer synthetic-token"},
        )
        handler = RegistryRedirect()
        redirected = handler.redirect_request(
            request,
            None,
            302,
            "Found",
            {},
            "https://pkg-npm.githubusercontent.com/test",
        )
        self.assertIsNone(redirected.get_header("Authorization"))
        for url in (
            "https://other.invalid/file",
            "http://pkg-npm.githubusercontent.com/file",
        ):
            with self.assertRaises(ValueError):
                handler.redirect_request(request, None, 302, "Found", {}, url)

    def test_public_release_download_is_anonymous_and_checksum_pinned(self):
        data = b"synthetic package bytes"
        plugin = self.plugin | {"sha256": digest(data)}
        response = MagicMock()
        response.__enter__.return_value.read.return_value = data
        opener = MagicMock()
        opener.open.return_value = response
        with patch("ingredients.urllib.request.build_opener", return_value=opener):
            with patch.dict("os.environ", GH_TOKEN="synthetic-must-not-be-sent"):
                self.assertEqual(download_package(plugin), data)
            request = opener.open.call_args.args[0]
            self.assertEqual(request.full_url, plugin["url"])
            self.assertIsNone(request.get_header("Authorization"))
            response.__enter__.return_value.read.return_value = b"changed"
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                download_package(plugin)

    def test_public_release_redirects_reject_unapproved_hosts_and_auth(self):
        handler = ReleaseRedirect()
        request = urllib.request.Request(
            self.plugin["url"], headers={"Authorization": "synthetic"}
        )
        redirected = handler.redirect_request(
            request,
            None,
            302,
            "Found",
            {},
            "https://release-assets.githubusercontent.com/asset?signature=synthetic",
        )
        self.assertIsNone(redirected.get_header("Authorization"))
        for url in (
            "http://github.com/asset",
            "https://other.invalid/asset",
            "https://github.com.other.invalid/asset",
        ):
            with self.assertRaises(ValueError):
                handler.redirect_request(request, None, 302, "Found", {}, url)

    def test_public_release_url_cannot_change_repository_or_version(self):
        for url in (
            self.plugin["url"].replace("v0.2.3", "latest"),
            self.plugin["url"].replace(
                "openclaw-connections/releases", "other/releases"
            ),
            self.plugin["url"] + "?redirect=elsewhere",
            "https://other.invalid/package.tgz",
        ):
            with self.assertRaisesRegex(ValueError, "public plugin URL"):
                plugin_selections([self.plugin | {"url": url}], 5)

    def test_external_pins_and_unique_ids_are_required(self):
        for changes in (
            {"version": "latest"},
            {"sha256": "abc"},
            {"id": "../escape"},
            {
                "source": {
                    "repository": self.plugin["source"]["repository"],
                    "commit": "main",
                }
            },
            {
                "source": {
                    "repository": "https://github.com/someone/other.git",
                    "commit": "1" * 40,
                }
            },
            {"untrackedRecipe": "anything"},
        ):
            plugin = self.plugin | changes
            with self.assertRaises(ValueError):
                plugin_selections([plugin], 3)
        with self.assertRaises(ValueError):
            plugin_selections([self.plugin, self.plugin["id"]], 3)
        with self.assertRaises(ValueError):
            plugin_selections([self.plugin], 2)

    def test_archive_traversal_links_and_duplicates_rejected(self):
        for name, link, duplicate in (
            ("package/../escape", False, False),
            ("package/link", True, False),
            ("package/same", False, True),
        ):
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
                package_files(
                    data.getvalue(), self.plugin | {"sha256": digest(data.getvalue())}
                )
