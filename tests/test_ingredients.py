"""Native ingredient integrity, archive boundaries and release-bound preset wiring."""
import io
import json
import subprocess
import sys
import tarfile
import unittest
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from common import digest, load
from ingredients import RegistryRedirect, package_files, plugin_selections
from release import latest_definition, preset_selection


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

    def test_runtime_uses_declared_plugin_api_range_without_losing_identity_checks(self):
        files = package_files(self.archive.read_bytes(), self.plugin)
        data = {"pkg": json.loads(files["package.json"]),
                "manifest": json.loads(files["openclaw.plugin.json"]), "selected": self.plugin}
        script = r'''
          import assert from 'node:assert/strict';
          import {readFileSync} from 'node:fs';
          import {execFileSync} from 'node:child_process';
          import {createRequire} from 'node:module';
          import {join} from 'node:path';
          import {verifyPluginCompatibility as verify} from './scripts/ingredients-runtime.mjs';
          const semver = createRequire(join(execFileSync('npm',['root','-g'],{encoding:'utf8'}).trim(),'npm/package.json'))('semver');
          const {pkg,manifest,selected}=JSON.parse(readFileSync(0,'utf8'));
          for (const host of ['2026.9.8','2026.9.9','2026.10.2']) verify(pkg,manifest,selected,host,semver);
          for (const host of ['2026.9.7','2026.10.3','invalid']) assert.throws(()=>verify(pkg,manifest,selected,host,semver));
          for (const change of [
            p=>p.name='other', p=>p.version='99.0.0',
            p=>p.openclaw.build.pluginSdkVersion=undefined,
            p=>p.openclaw.build.pluginSdkVersion='0.0.0',
            p=>p.openclaw.compat.pluginApi='',
            p=>p.openclaw.compat.pluginApi='invalid',
            p=>p.openclaw.compat.pluginApi='>=2026.10.2',
            p=>p.openclaw.compat.minGatewayVersion='2026.10.2',
          ]) {
            const copy=structuredClone(pkg); change(copy);
            assert.throws(()=>verify(copy,manifest,selected,'2026.9.9',semver));
          }
          assert.throws(()=>verify(pkg,{...manifest,id:'other'},selected,'2026.9.9',semver));
          const legacy=structuredClone(pkg);delete legacy.openclaw.compat;
          verify(legacy,manifest,selected,'2026.9.8',semver);
          assert.throws(()=>verify(legacy,manifest,selected,'2026.9.9',semver));
        '''
        subprocess.run(["node", "--input-type=module", "-e", script], cwd=ROOT,
                       input=json.dumps(data), text=True, check=True, capture_output=True)

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

    def test_missing_plugin_code_or_ui_is_not_an_unconfigured_plugin(self):
        with tarfile.open(self.archive) as original:
            ui = json.load(original.extractfile("package/openclaw.plugin.json"))["controlUi"]["entry"]
            members = [(member, original.extractfile(member).read() if member.isfile() else None)
                       for member in original.getmembers()]
        for missing in ("package/dist/index.js", "package/openclaw.plugin.json", "package/" + ui):
            data = io.BytesIO()
            with tarfile.open(fileobj=data, mode="w:gz") as archive:
                for member, content in members:
                    if member.name != missing:
                        archive.addfile(member, io.BytesIO(content) if content is not None else None)
            with self.assertRaises((ValueError, KeyError)):
                package_files(data.getvalue(), self.plugin | {"sha256": digest(data.getvalue())})

    def test_selected_presets_are_single_image_ingredients(self):
        release = load(ROOT / ".work/resolved/candidate.json")
        self.assertEqual([p["name"] for p in release["presets"]], [load(ROOT / p["path"])["name"] for p in preset_selection(self.spec)[1]])
        self.assertFalse(any(p.endswith("-preset.json") for p in release["payloadFiles"]))
        for preset in release["presets"]:
            source = ROOT / ".work/resolved/source" / preset["path"].removeprefix("/app/")
            self.assertEqual(digest(source.read_bytes()), preset["sha256"])
