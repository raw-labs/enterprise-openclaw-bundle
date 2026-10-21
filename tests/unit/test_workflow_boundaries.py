"""Exercise checked-in job conditions without dispatching workflows or using credentials."""

import json
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPOSITORY = "raw-labs/enterprise-openclaw-bundle"


def job_block(document, name):
    block = document.split("  " + name + ":\n", 1)[1]
    return re.split(r"(?m)^  [\w-]+:\s*$", block, maxsplit=1)[0]


class WorkflowBoundaries(unittest.TestCase):
    def test_forks_and_pull_requests_cannot_enter_trusted_jobs(self):
        validation = (ROOT / ".github/workflows/validate.yml").read_text()
        release = (ROOT / ".github/workflows/release.yml").read_text()
        cases = []
        for name, document in (
            ("validate", validation),
            ("resolve", release),
            ("native", release),
            ("review", release),
            ("handoff", release),
        ):
            condition = re.search(r"(?m)^    if: (.+)$", job_block(document, name))[1]
            for private in (False, True):
                for repository in (REPOSITORY, "fork/bundle"):
                    for event in (
                        "pull_request",
                        "push",
                        "workflow_dispatch",
                        "pull_request_target",
                    ):
                        for ref in (
                            "refs/heads/main",
                            "refs/heads/topic",
                            "refs/heads/codex/review",
                            "refs/pull/1/merge",
                        ):
                            for publish in (False, True):
                                trusted = (
                                    repository == REPOSITORY
                                    and event
                                    == (
                                        "push"
                                        if name == "validate"
                                        else "workflow_dispatch"
                                    )
                                )
                                if name == "validate" or name == "handoff":
                                    expected = trusted and ref == "refs/heads/main"
                                elif name == "review":
                                    expected = (
                                        trusted
                                        and not publish
                                        and ref.startswith("refs/heads/codex/")
                                    )
                                else:
                                    expected = trusted and (
                                        ref == "refs/heads/main"
                                        or (
                                            not publish
                                            and ref.startswith("refs/heads/codex/")
                                        )
                                    )
                                cases.append(
                                    {
                                        "name": name,
                                        "condition": condition,
                                        "expected": expected,
                                        "inputs": {"publish": publish},
                                        "github": {
                                            "event_name": event,
                                            "repository": repository,
                                            "ref": ref,
                                            "event": {
                                                "repository": {"private": private}
                                            },
                                        },
                                    }
                                )
        # These conditions use the common Boolean/equality subset of GitHub and JS.
        subprocess.run(
            [
                "node",
                "--input-type=module",
                "-e",
                """
                import assert from 'node:assert/strict';
                import {readFileSync} from 'node:fs';
                for (const fixture of JSON.parse(readFileSync(0, 'utf8'))) {
                    const evaluate = new Function('github', 'inputs', 'startsWith', 'return Boolean(' + fixture.condition + ')');
                    assert.equal(evaluate(fixture.github, fixture.inputs, (value, prefix) => value.startsWith(prefix)), fixture.expected,
                        fixture.name + ': ' + JSON.stringify(fixture.github));
                }
            """,
            ],
            input=json.dumps(cases),
            text=True,
            check=True,
            capture_output=True,
        )

    def test_contributor_job_has_no_credentialed_or_paid_steps(self):
        document = (ROOT / ".github/workflows/validate.yml").read_text()
        contributor = job_block(document, "contributor")
        self.assertIn("runs-on: ubuntu-24.04", contributor)
        self.assertIn("permissions:\n  contents: read", document)
        for forbidden in (
            "secrets.",
            "packages:",
            "depot-",
            "scripts/release.py",
            "pull_request_target",
        ):
            self.assertNotIn(forbidden, contributor)
        self.assertNotIn("pull_request_target:", document)

    def test_branch_review_job_cannot_publish(self):
        document = (ROOT / ".github/workflows/release.yml").read_text()
        review = job_block(document, "review")
        self.assertIn("contents: read", review)
        self.assertIn("packages: read", review)
        for forbidden in (
            "contents: write",
            "packages: write",
            " publish ",
            "gh release",
        ):
            self.assertNotIn(forbidden, review)

    def test_raw_diagnostics_are_never_uploaded_from_public_ci(self):
        document = (ROOT / ".github/workflows/release.yml").read_text()
        for name in ("native", "review", "handoff"):
            block = job_block(document, name)
            diagnostic = re.search(r"(?ms)^      - name: Retain failed .*?(?=^      - |\Z)", block)[0]
            self.assertIn("if: failure() && github.event.repository.private", diagnostic)
        for name in ("validate.yml", "release.yml"):
            document = (ROOT / ".github/workflows" / name).read_text()
            self.assertIn("BUNDLE_DISTRIBUTION_VISIBILITY: ${{ github.event.repository.private && 'private' || 'public' }}", document)
