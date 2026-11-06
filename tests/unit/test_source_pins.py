"""Source format admission; synthetic pins never qualify an image."""
import copy
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from common import openclaw_source, save, confinement_profile


class SourcePins(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.runtime = self.root / "deploy/runtime"
        self.runtime.mkdir(parents=True)
        self.pins = {"commit": "1" * 40, "sourceArchiveSha256": "2" * 64,
                     "buildTimestamp": "2026-11-04T17:24:42Z"}

    def test_native_manifest_and_historical_recipe(self):
        save(self.runtime / "openclaw-source.json", self.pins)
        self.assertEqual(openclaw_source(self.root), self.pins)
        (self.runtime / "openclaw-source.json").unlink()
        (self.runtime / "Dockerfile").write_text(
            'ARG OPENCLAW_COMMIT=' + '1' * 40 + '\n'
            + "RUN echo '" + '2' * 64 + "  /tmp/openclaw-source.tar.gz' | sha256sum --check\n")
        self.assertEqual(openclaw_source(self.root), {k:v for k,v in self.pins.items() if k != 'buildTimestamp'})

    def test_invalid_manifest_never_falls_back_to_recipe(self):
        for change in ({"commit": "main"}, {"sourceArchiveSha256": "unpinned"},
                       {"buildTimestamp": "today"}, {"unexpected": True}):
            pins = copy.deepcopy(self.pins)
            pins.update(change)
            save(self.runtime / "openclaw-source.json", pins)
            with self.assertRaises(ValueError):
                openclaw_source(self.root)

    def test_typescript_policy_requires_wrapper_and_reviewed_apparmor(self):
        inputs = {"scripts/lib/codex-seccomp-profile.mjs": "1" * 64,
                  "scripts/lib/codex-seccomp-profile.ts": "2" * 64,
                  "scripts/ci/codex-bwrap.apparmor": "3" * 64}
        confinement_profile(inputs)
        del inputs['scripts/lib/codex-seccomp-profile.mjs']
        with self.assertRaises(ValueError):
            confinement_profile(inputs)
