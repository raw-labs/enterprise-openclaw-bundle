"""Qualify an OCE candidate using exact-source CI and bounded native receipts."""

import hashlib
import json
import os
import re
import sys
from pathlib import Path

from oce_evidence import (
    REPOSITORY,
    api,
    artifact_json,
    command,
    pages,
    save,
    wait_runs,
    workflow_run,
)


def require_jobs(run_id, names):
    jobs = pages(f"repos/{REPOSITORY}/actions/runs/{run_id}/jobs?filter=latest", "jobs")
    for name in names:
        matches = [job for job in jobs if job["name"] == name]
        if len(matches) != 1 or matches[0]["conclusion"] != "success":
            raise RuntimeError("Missing successful exact-source job: " + name)
    return [
        {"id": job["id"], "name": job["name"], "conclusion": job["conclusion"]}
        for job in jobs
    ]


def validate_lane(summary, sha, zero_skips=False):
    if (
        summary.get("sourceSha") != sha
        or summary.get("status") != "passed"
        or summary.get("exitCode") != 0
        or summary.get("issues")
    ):
        raise RuntimeError(
            "Invalid same-source lane evidence: " + str(summary.get("lane"))
        )
    if zero_skips and (summary["counts"]["skipped"] or summary["counts"]["todo"]):
        raise RuntimeError("Required lane contains skipped proof: " + summary["lane"])
    for file in summary.get("files", []):
        if (
            file["status"] != "passed"
            or file.get("issues")
            or file.get("cleanup")
            and file["cleanup"]["status"] != "passed"
        ):
            raise RuntimeError("File failed or did not clean up: " + file["path"])


def require_case(summaries, pattern):
    matches = [
        case
        for summary in summaries.values()
        for file in summary.get("files", [])
        for case in file.get("tests", [])
        if re.search(pattern, case["name"], re.IGNORECASE)
    ]
    if not matches or any(case["status"] != "passed" for case in matches):
        raise RuntimeError("Required scenario missing or did not pass: " + pattern)
    return [case["name"] for case in matches]


def source(sha, branch, state):
    runs = [
        workflow_run(workflow, sha, branch, state)
        for workflow in ("ci.yml", "codeql.yml")
    ]
    runs = wait_runs(runs, sha, state)
    ci, codeql = runs
    jobs = require_jobs(ci["id"], ["CI Required", "First Agent Smoke"])
    require_jobs(codeql["id"], ["CodeQL (javascript-typescript)", "CodeQL (actions)"])
    manifest = json.loads(Path("scripts/ci/test-suites.json").read_text())
    lanes = manifest["groups"]["ci"]
    summaries = {}
    results = state / "results"
    results.mkdir(exist_ok=True)
    artifacts = pages(
        f"repos/{REPOSITORY}/actions/runs/{ci['id']}/artifacts", "artifacts"
    )
    for artifact in artifacts:
        if not artifact["name"].startswith("ci-results-") or artifact["expired"]:
            continue
        for _filename, summary in artifact_json(
            artifact, lambda name: Path(name).name in {lane + ".json" for lane in lanes}
        ):
            lane = summary.get("lane")
            if lane in summaries:
                raise RuntimeError("Ambiguous duplicate lane artifact: " + str(lane))
            validate_lane(
                summary,
                sha,
                lane
                in {
                    "postgres",
                    "postgres-auth",
                    "k3d-fixture-state",
                    "images-runtime-startup",
                    "checks-browser-2",
                },
            )
            summaries[lane] = summary
            save(results / (lane + ".json"), summary)
    if set(summaries) != set(lanes):
        raise RuntimeError(
            "Missing canonical full-mode lane receipts: "
            + str(sorted(set(lanes) - set(summaries)))
        )
    # Reuse the actual candidate's canonical aggregation/coverage validator.
    aggregate = json.loads(
        command(
            [
                "node",
                "scripts/ci/run-tests.mjs",
                "aggregate",
                "ci",
                "--results-dir",
                str(results),
            ],
            env={**os.environ, "GITHUB_SHA": sha},
        )
    )
    if (
        aggregate["sourceSha"] != sha
        or aggregate["status"] != "passed"
        or aggregate["issues"]
    ):
        raise RuntimeError("Canonical aggregate did not qualify the candidate")
    save(state / "canonical-aggregate.json", aggregate)
    required = [
        r"real Kubernetes Drivers safely use and preserve an externally managed tenant namespace",
        r"provisioning API retains the first deployment outcome with real Kubernetes fixture storage",
        r"trusted embedded channel opt-in projects exact Secrets through API provisioning, revisions and stop",
        r"Teams directory selects names.*\(chromium\)",
        r"Teams directory selects names.*\(webkit\)",
        r"runtime image downloads native guarded Teams media through the channel proxy",
    ]
    cases = {pattern: require_case(summaries, pattern) for pattern in required}
    for name in (
        "native-admin-session.test.mjs",
        "postgres-migration-compatibility.test.mjs",
    ):
        files = [
            file
            for summary in summaries.values()
            for file in summary.get("files", [])
            if Path(file["path"]).name == name
        ]
        if not files or any(
            file["counts"]["skipped"] or file["counts"]["todo"] for file in files
        ):
            raise RuntimeError(
                "Required authority/upgrade file missing or skipped: " + name
            )
    return {
        "runs": [{"id": run["id"], "url": run["html_url"]} for run in runs],
        "jobs": jobs,
        "lanes": {lane: summary["counts"] for lane, summary in summaries.items()},
        "required_cases": cases,
        "aggregate_sha256": hashlib.sha256(
            (state / "canonical-aggregate.json").read_bytes()
        ).hexdigest(),
    }


def validate_platforms(receipts, sha, run_id):
    expected = {
        (image, "linux/" + arch)
        for image in ("controller", "runtime")
        for arch in ("amd64", "arm64")
    }
    observed = set()
    for receipt in receipts:
        pair = (receipt["image"], receipt["platform"])
        if pair in observed or pair not in expected:
            raise RuntimeError("Duplicate or unexpected native platform receipt")
        observed.add(pair)
        if (
            receipt["sourceSha"] != sha
            or receipt["workflowSha"] != sha
            or str(receipt["runId"]) != str(run_id)
            or receipt["native"] is not True
            or not re.fullmatch(r"sha256:[a-f0-9]{64}", receipt["digest"])
        ):
            raise RuntimeError(
                "Native receipt source/run/digest does not match qualification"
            )
    if observed != expected:
        raise RuntimeError("Incomplete native controller/runtime platform set")


def native(sha, branch, state):
    run = workflow_run("container-check.yml", sha, branch, state)
    run = wait_runs([run], sha, state)[0]
    names = [
        f"Prepare {image} ({arch})"
        for image in ("controller", "runtime")
        for arch in ("amd64", "arm64")
    ]
    jobs = require_jobs(run["id"], names)
    receipts = []
    for artifact in pages(
        f"repos/{REPOSITORY}/actions/runs/{run['id']}/artifacts", "artifacts"
    ):
        if artifact["name"].startswith("platform-") and not artifact["expired"]:
            entries = artifact_json(
                artifact, lambda name: Path(name).name == "platform.json"
            )
            if len(entries) != 1:
                raise RuntimeError("Native artifact lacks one unique platform.json")
            receipts.append(entries[0][1])
    validate_platforms(receipts, sha, run["id"])
    save(state / "platforms.json", receipts)
    return {
        "run": {"id": run["id"], "url": run["html_url"]},
        "jobs": jobs,
        "platforms": receipts,
    }


def main():
    sha = os.environ["MAINTAIN_SOURCE_SHA"]
    inputs = json.loads(Path(os.environ["MAINTAIN_INPUTS_FILE"]).read_text())
    state = Path(os.environ["MAINTAIN_CHECK_STATE_DIR"])
    if inputs["fork"] != f"https://github.com/{REPOSITORY}.git":
        raise RuntimeError("This recipe only dispatches to its reviewed OCE fork")
    actor = api("user")["login"]
    if actor != "miguelbranco80":
        raise RuntimeError("Unexpected GitHub identity")
    function = {"source": source, "native": native}[sys.argv[1]]
    evidence = function(sha, inputs["candidate_branch"], state)
    save(state / "receipt.json", {"source_sha": sha, "details": evidence})


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Avoid rendering urllib request URLs, which can contain signed tokens.
        if isinstance(error, (OSError,)):
            print(
                f"Hosted evidence transport failed ({type(error).__name__}); resume the recorded check",
                file=sys.stderr,
            )
        else:
            print(str(error), file=sys.stderr)
        raise SystemExit(1) from None
