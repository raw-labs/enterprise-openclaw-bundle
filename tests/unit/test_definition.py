"""Definition boundaries and genuine generated inventory; no runtime qualification fixtures."""

import copy
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from common import (  # noqa: E402
    APPARMOR_PROFILES,
    confinement_profile,
    load,
    save,
)
from release import (  # noqa: E402
    definition,
    latest_definition,
    pinned_file,
    preflight,
    preset_selection,
)
from stock import publish  # noqa: E402

from tests.unit.support import candidate  # noqa: E402


class DefinitionInputs(unittest.TestCase):
    def setUp(self):
        self.path = latest_definition()
        self.spec = load(self.path)

    def rejected(self, mutate):
        spec = copy.deepcopy(self.spec)
        mutate(spec)
        with patch(
            "release.load",
            side_effect=lambda path: spec if Path(path) == self.path else load(path),
        ):
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

    def test_confinement_requires_one_complete_known_policy_layout(self):
        seccomp = {"scripts/lib/codex-seccomp-profile.mjs": "1" * 64}
        for path, profile in APPARMOR_PROFILES.items():
            self.assertEqual(
                confinement_profile(seccomp | {path: "2" * 64}), (path, profile)
            )
        for inputs in (
            {},
            seccomp,
            {next(iter(APPARMOR_PROFILES)): "2" * 64},
            seccomp | {path: "2" * 64 for path in APPARMOR_PROFILES},
            seccomp | {"../unreviewed.apparmor": "2" * 64},
            seccomp | {"scripts/ci/codex-bwrap.apparmor": "not-a-hash"},
        ):
            with self.assertRaises(ValueError):
                confinement_profile(inputs)

    def test_codex_prereleases_and_upgrade_baseline_are_explicit(self):
        self.assertEqual(self.spec["schemaVersion"], 5)
        for version in ("0.163.0", "0.163.0-alpha.2", "0.163.0-beta.1", "0.163.0-rc.0"):
            with patch(
                "release.load",
                side_effect=lambda path, version=version: (
                    self.spec | {"codexVersion": version}
                    if Path(path) == self.path
                    else load(path)
                ),
            ):
                definition(self.path)
        for mutate in (
            lambda s: s.update(codexVersion="latest"),
            lambda s: s.update(codexVersion="0.163.0-alpha.02"),
            lambda s: s.update(codexVersion="0.163.0-alpha.2+unreviewed"),
            lambda s: s.update(schemaVersion=4),
            lambda s: s["build"].update(upgradeFrom=s["version"]),
            lambda s: s["build"].update(upgradeFrom="latest"),
        ):
            self.rejected(mutate)

    def test_preset_policy_and_enabled_plugin_must_match_selection(self):
        for mutate in (
            lambda s: s["presets"].update(includeDefaults="false"),
            lambda s: s["presets"].update(files={}),
            lambda s: s["presets"].update(default="unknown"),
            lambda s: s.update(plugins=["codex", "slack"]),
        ):
            self.rejected(mutate)
        self.assertFalse(preset_selection(self.spec)[0])

    def test_all_definitions_have_one_complete_selection(self):
        paths = list((ROOT / "bundles").glob("*/bundle.json"))
        self.assertTrue(paths)
        for path in paths:
            spec = definition(path)
            self.assertTrue(
                {"patches", "confinement"}
                <= set(spec["build"])
                <= {"patches", "confinement", "upgradeFrom"}
            )
            self.assertNotIn("recipe", spec)
            self.assertNotIn("installationExample", spec)


class ReleaseDestination(unittest.TestCase):
    def test_visibility_mismatch_rejected_before_any_publication_work(self):
        for actual, api_visibility, expected, selected in (
            (True, "private", "public", "public"),
            (False, "public", "private", "private"),
            (True, "private", "private", "public"),
            (False, "public", "public", "private"),
            (True, "private", "internal", "private"),
            (True, "internal", "private", "private"),
            (False, "internal", "public", "public"),
            (True, None, "private", "private"),
        ):
            release = candidate()
            release["distribution"]["visibility"] = selected
            with (
                self.subTest(actual=actual, api_visibility=api_visibility, expected=expected, selected=selected),
                patch.dict("os.environ", {
                    "GITHUB_REPOSITORY": "raw-labs/enterprise-openclaw-bundle",
                    "GITHUB_REF": "refs/heads/main",
                    "BUNDLE_DISTRIBUTION_VISIBILITY": expected,
                }),
                patch("stock.github_json", return_value={"private": actual, "visibility": api_visibility}),
                patch("stock.inspect_oci") as inspect,
                patch("stock.run") as registry_write,
            ):
                with self.assertRaises(ValueError):
                    publish(SimpleNamespace(command="publish"), release)
                inspect.assert_not_called()
                registry_write.assert_not_called()

    def test_preflight_accepts_both_visibilities_but_rejects_destination_changes(self):
        sha = "1" * 40
        for visibility in ("private", "public"):
            repo = {"full_name": "raw-labs/enterprise-openclaw-bundle",
                    "private": visibility == "private", "visibility": visibility,
                    "default_branch": "main"}
            run = {"head_sha": sha, "actor": {"login": "publisher"},
                   "triggering_actor": {"login": "publisher"}}
            head = {"object": {"sha": sha}}

            def github(endpoint):
                if endpoint.endswith("actions/runs/42"):
                    return run
                if endpoint.endswith("heads/main"):
                    return head
                if "/tags/" in endpoint:
                    return None
                return repo

            with (
                patch.dict("os.environ", {
                    "GITHUB_REPOSITORY": repo["full_name"], "GITHUB_REF": "refs/heads/main",
                    "GITHUB_ACTOR": "publisher", "GITHUB_RUN_ID": "42",
                    "BUNDLE_DISTRIBUTION_VISIBILITY": visibility,
                }),
                patch("release.github_json", side_effect=github),
                patch("release.subprocess.check_output",
                      return_value="https://github.com/raw-labs/enterprise-openclaw-bundle.git\n") as origin,
            ):
                preflight("v0.1.0-alpha.99", sha)
                repo["private"] = not repo["private"]
                with self.assertRaisesRegex(ValueError, "visibility"):
                    preflight("v0.1.0-alpha.99", sha)
                repo["private"] = not repo["private"]
                head["object"]["sha"] = "2" * 40
                with self.assertRaisesRegex(ValueError, "remote main changed"):
                    preflight("v0.1.0-alpha.99", sha)
                head["object"]["sha"] = sha
                run["actor"]["login"] = run["triggering_actor"]["login"] = "someone-else"
                with self.assertRaisesRegex(ValueError, "identity mismatch"):
                    preflight("v0.1.0-alpha.99", sha)
                run["actor"]["login"] = "publisher"
                origin.return_value = "https://github.com/someone/else.git\n"
                with self.assertRaisesRegex(ValueError, "unexpected origin"):
                    preflight("v0.1.0-alpha.99", sha)

    def test_existing_tag_or_changed_remote_head_rejected_before_build(self):
        sha = "1" * 40
        env = {
            "BUNDLE_DISTRIBUTION_VISIBILITY": "private",
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
                "visibility": "private",
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
        release = candidate()
        with tempfile.TemporaryDirectory() as temp:
            selection = Path(temp) / "candidate.json"
            save(selection, release)
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
