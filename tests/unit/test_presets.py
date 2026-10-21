"""Reject weakening the curated templates even when ingredient hashes are updated."""

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from presets import reviewed_preset  # noqa: E402


class CuratedPolicy(unittest.TestCase):
    def preset(self, name):
        return json.loads((ROOT / "presets" / (name + "-preset.json")).read_text())

    def test_optional_features_and_elevated_tools_require_opt_in(self):
        for name in ("assistant", "coding"):
            preset = self.preset(name)
            reviewed_preset(preset)
            for mutation in (
                lambda v: v["browser"].update(enabled=True),
                lambda v: v["browser"].update(noSandbox=True),
                lambda v: v["gateway"]["controlUi"]["experimental"].update(
                    customPlugins=True
                ),
                lambda v: v["plugins"]["entries"].update(slack={"enabled": True}),
                lambda v: v["tools"]["elevated"].update(enabled=True),
                lambda v: v["tools"]["alsoAllow"].append("browser"),
            ):
                with self.subTest(preset=name, mutation=mutation):
                    changed = copy.deepcopy(preset)
                    mutation(changed["template"]["configuration"]["values"])
                    with self.assertRaises(ValueError):
                        reviewed_preset(changed)

    def test_coding_cannot_bypass_approvals_or_network_policy(self):
        original = self.preset("coding")
        for mutation in (
            lambda a: a.update(approvalPolicy="never"),
            lambda a: a.update(approvalsReviewer="auto"),
            lambda a: a.update(sandbox="danger-full-access"),
            lambda a: a["networkProxy"].update(enabled=False),
            lambda a: a["networkProxy"].update(mode="full"),
            lambda a: a["networkProxy"].update(domains={"*": "allow"}),
            lambda a: a["networkProxy"].update(domains={"*.example.invalid": "allow"}),
            lambda a: a["networkProxy"].update(domains={"127.0.0.1": "allow"}),
            lambda a: a["networkProxy"].update(domains={}),
            lambda a: a["networkProxy"].update(enableSocks5=True),
            lambda a: a["networkProxy"].update(allowUpstreamProxy=True),
            lambda a: a["networkProxy"].update(unixSockets={"/tmp/test.sock": "allow"}),
        ):
            with self.subTest(mutation=mutation):
                changed = copy.deepcopy(original)
                app = changed["template"]["configuration"]["values"]["plugins"][
                    "entries"
                ]["codex"]["config"]["appServer"]
                mutation(app)
                with self.assertRaises(ValueError):
                    reviewed_preset(changed)

    def test_coding_fetch_and_live_search_cannot_bypass_the_proxy(self):
        for mutation in (
            lambda w: w["fetch"].update(enabled=True),
            lambda w: w["search"]["openaiCodex"].update(mode="live"),
        ):
            changed = self.preset("coding")
            mutation(changed["template"]["configuration"]["values"]["tools"]["web"])
            with self.assertRaises(ValueError):
                reviewed_preset(changed)

    def test_site_example_does_not_enable_experimental_channels(self):
        site = json.loads((ROOT / "docs/examples/installations/site.json").read_text())
        self.assertFalse(site["channels"]["experimentalEmbeddedChannels"])
