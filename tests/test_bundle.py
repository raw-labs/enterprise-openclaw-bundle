"""Observable release safety and artifact behavior; no simulated runtime claims."""

import copy
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from common import install_gate, read_release, validate  # noqa: E402


class ReleaseContract(unittest.TestCase):
    def setUp(self):
        self.release = read_release(ROOT / "releases/pilot-baseline.json", ROOT)

    def reject(self, change):
        release = copy.deepcopy(self.release)
        change(release)
        with self.assertRaises(ValueError):
            validate(release)

    def test_moving_source_tag_rejected(self):
        self.reject(lambda r: r["sources"]["oce"].update(commit="main"))

    def test_mutable_image_rejected(self):
        self.reject(
            lambda r: r["images"]["runtime"].update(
                reference="registry.example/runtime:latest"
            )
        )

    def test_each_role_source_mismatch_rejected(self):
        for role in self.release["images"]:
            with self.subTest(role=role):
                self.reject(
                    lambda r, role=role: r["images"][role].update(oceCommit="0" * 40)
                )

    def test_chart_source_mismatch_rejected(self):
        self.reject(lambda r: r["chart"].update(sourceCommit="0" * 40))

    def test_codex_metadata_mismatch_rejected(self):
        self.reject(lambda r: r["images"]["runtime"].update(codexVersion="0.158.0"))

    def test_evidence_cannot_follow_changed_digest(self):
        self.reject(
            lambda r: r["images"]["runtime"].update(
                reference=r["images"]["runtime"]["reference"].split("@")[0]
                + "@sha256:"
                + "0" * 64
            )
        )

    def test_pilot_cannot_claim_customer_qualification(self):
        self.reject(lambda r: r["qualification"].update(customerQualified=True))

    def test_pilot_requires_explicit_acceptance(self):
        with self.assertRaises(ValueError):
            install_gate(self.release, False)
        install_gate(self.release, True)

    def test_candidate_cannot_be_installed(self):
        self.release["qualification"] = {
            "status": "unqualified",
            "customerQualified": False,
        }
        self.release["kind"] = "candidate"
        validate(self.release)
        with self.assertRaises(ValueError):
            install_gate(self.release, True)

    def test_false_qualification_without_receipt_rejected(self):
        self.reject(
            lambda r: (
                r.update(kind="release"),
                r["qualification"].update(status="qualified"),
            )
        )


class ArtifactBehavior(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = ROOT / ".work/verified-source"
        if not cls.source.exists():
            raise RuntimeError(
                "Run pinned source export to .work/verified-source before tests; no packaging tests are skipped"
            )
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name)
        for name in ["one", "two"]:
            cls.command(
                [
                    "scripts/bundle.py",
                    "--release",
                    "releases/pilot-baseline.json",
                    "package",
                    "--source",
                    cls.source,
                    "--output",
                    cls.out / (name + ".tar.gz"),
                ]
            )
        with tarfile.open(cls.out / "one.tar.gz") as tar:
            tar.extractall(cls.out / "unpacked", filter="data")
        cls.artifact = cls.out / "unpacked" / "pilot-baseline-2026-10-07"

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    @classmethod
    def command(cls, args, ok=True):
        result = subprocess.run(
            [sys.executable, *map(str, args)], cwd=ROOT, text=True, capture_output=True
        )
        if (result.returncode == 0) != ok:
            raise AssertionError(result.stdout + result.stderr)
        return result

    def installer(self, *args, ok=True):
        return self.command([self.artifact / "scripts/install.py", *args], ok=ok)

    def test_archive_reproducibility(self):
        self.assertEqual(
            (self.out / "one.tar.gz").read_bytes(),
            (self.out / "two.tar.gz").read_bytes(),
        )

    def test_contents_and_integrity(self):
        self.installer("verify")
        names = {
            str(p.relative_to(self.artifact))
            for p in self.artifact.rglob("*")
            if p.is_file()
        }
        self.assertIn("notices/OCE-LICENSE", names)
        self.assertIn("chart/openclaw-enterprise-0.1.0.tgz", names)
        self.assertFalse(
            any(
                n.startswith("overlays/")
                or "package-lock" in n
                or n.endswith(".tfstate")
                for n in names
            )
        )
        self.assertFalse((self.artifact / "releases/source-files.json").exists())

    def test_both_supported_profiles_render(self):
        for profile in ["openclaw", "codex"]:
            out = self.out / ("render-" + profile)
            self.installer(
                "render",
                "--input",
                ROOT / "profiles/aws-example.json",
                "--profile",
                profile,
                "--output",
                out,
                "--allow-pilot-baseline",
            )
            self.assertIn("kind: Deployment", (out / "rendered.yaml").read_text())
            if profile == "codex":
                self.assertIn(
                    "catalogSource: openai-curated",
                    (out / "installation.yaml").read_text(),
                )
            self.installer("check", "--directory", out)

    def test_aws_ingress_uses_only_reviewed_proxy_peers(self):
        out = self.out / "aws-ingress"
        self.installer(
            "render",
            "--input",
            ROOT / "profiles/aws-example.json",
            "--profile",
            "codex",
            "--output",
            out,
            "--allow-pilot-baseline",
        )
        policy = json.loads((out / "supplemental.json").read_text())["items"][0]
        peers = policy["spec"]["ingress"][0]["from"]
        site = json.loads((ROOT / "profiles/aws-example.json").read_text())
        self.assertEqual(
            [p["ipBlock"]["cidr"] for p in peers],
            site["controlPlane"]["trustedProxy"]["cidrs"],
        )
        self.assertEqual(
            policy["spec"]["podSelector"]["matchLabels"]["app.kubernetes.io/component"],
            "api",
        )

    def test_default_install_rejects_pilot(self):
        result = self.installer(
            "render",
            "--input",
            ROOT / "profiles/aws-example.json",
            "--profile",
            "codex",
            "--output",
            self.out / "no-opt-in",
            ok=False,
        )
        self.assertIn("requires --allow-pilot-baseline", result.stderr)

    def test_bad_installation_input_rejected(self):
        inp = json.loads((ROOT / "profiles/aws-example.json").read_text())
        inp["controlPlane"]["databaseCidrs"] = []
        file = self.out / "bad-site.json"
        file.write_text(json.dumps(inp))
        self.installer(
            "render",
            "--input",
            file,
            "--profile",
            "codex",
            "--output",
            self.out / "bad-render",
            "--allow-pilot-baseline",
            ok=False,
        )
        self.assertFalse((self.out / "bad-render/values.yaml").exists())

    def test_unknown_installation_field_rejected(self):
        inp = json.loads((ROOT / "profiles/aws-example.json").read_text())
        inp["secret"] = "never-allow-ignored-fields"
        file = self.out / "unknown-site.json"
        file.write_text(json.dumps(inp))
        self.installer(
            "render",
            "--input",
            file,
            "--profile",
            "codex",
            "--output",
            self.out / "unknown-render",
            "--allow-pilot-baseline",
            ok=False,
        )

    def test_installation_image_mismatch_rejected(self):
        inp = json.loads((ROOT / "profiles/aws-example.json").read_text())
        inp["runtime"]["image"] = "example/runtime@sha256:" + "0" * 64
        file = self.out / "bad-image-site.json"
        file.write_text(json.dumps(inp))
        result = self.installer(
            "render",
            "--input",
            file,
            "--profile",
            "codex",
            "--output",
            self.out / "bad-image",
            "--allow-pilot-baseline",
            ok=False,
        )
        self.assertIn("installation/release mismatch", result.stderr)

    def test_mirror_mismatch_rejected(self):
        release = json.loads((self.artifact / "release.json").read_text())
        refs = {r: i["reference"] for r, i in release["images"].items()}
        refs["runtime"] = "example/runtime@sha256:" + "0" * 64
        file = self.out / "bad-mirrors.json"
        file.write_text(json.dumps(refs))
        self.installer(
            "render",
            "--input",
            ROOT / "profiles/aws-example.json",
            "--mirrors",
            file,
            "--profile",
            "codex",
            "--output",
            self.out / "bad-mirror",
            "--allow-pilot-baseline",
            ok=False,
        )

    def test_digest_preserving_mirror_renders(self):
        release = json.loads((self.artifact / "release.json").read_text())
        refs = {
            r: "registry.example/customer/" + r + "@" + i["reference"].split("@")[1]
            for r, i in release["images"].items()
        }
        file = self.out / "mirrors.json"
        file.write_text(json.dumps(refs))
        out = self.out / "mirror-render"
        self.installer(
            "render",
            "--input",
            ROOT / "profiles/aws-example.json",
            "--mirrors",
            file,
            "--profile",
            "codex",
            "--output",
            out,
            "--allow-pilot-baseline",
        )
        self.assertIn(refs["controller"], (out / "rendered.yaml").read_text())

    def test_source_mutation_blocks_package(self):
        source = self.out / "changed-source"
        shutil.copytree(self.source, source)
        (source / "Dockerfile").write_text("FROM unexpected\n")
        result = self.command(
            [
                "scripts/bundle.py",
                "--release",
                "releases/pilot-baseline.json",
                "package",
                "--source",
                source,
                "--output",
                self.out / "bad-source.tar.gz",
            ],
            ok=False,
        )
        self.assertIn("differs from pinned inventory", result.stderr)

    def test_tampered_delivered_file_blocks_verification(self):
        artifact = self.out / "tampered"
        shutil.copytree(self.artifact, artifact)
        (artifact / "scripts/install.py").write_text(
            (artifact / "scripts/install.py").read_text() + "\n# altered\n"
        )
        self.command([artifact / "scripts/install.py", "verify"], ok=False)

    def test_paired_installation_checksum_enforced(self):
        out = self.out / "changed-config"
        self.installer(
            "render",
            "--input",
            ROOT / "profiles/aws-example.json",
            "--profile",
            "openclaw",
            "--output",
            out,
            "--allow-pilot-baseline",
        )
        with (out / "installation.yaml").open("a") as f:
            f.write("\n# changed\n")
        self.installer("check", "--directory", out, ok=False)


if __name__ == "__main__":
    unittest.main()
