"""Structural source audit and published migration-prefix guard, not runtime proof."""

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

from oce_evidence import REPOSITORY, api


def git(*args):
    return subprocess.check_output(["git", *args])


def check_prefix(previous):
    path = "migrations/meta/_journal.json"
    old = json.loads(git("show", f"{previous}:{path}"))
    new = json.loads(Path(path).read_text())
    if {k: v for k, v in old.items() if k != "entries"} != {
        k: v for k, v in new.items() if k != "entries"
    }:
        raise RuntimeError("Published migration journal metadata changed")
    prefix = old["entries"]
    if new["entries"][: len(prefix)] != prefix:
        raise RuntimeError(
            "Published migration identities/order/metadata were rewritten"
        )
    hashes = {}
    for entry in prefix:
        path = f"migrations/{entry['tag']}.sql"
        published = git("show", f"{previous}:{path}")
        if Path(path).read_bytes() != published:
            raise RuntimeError("Published migration SQL changed: " + path)
        hashes[path] = hashlib.sha256(published).hexdigest()
    tags = [entry["tag"] for entry in new["entries"]]
    indices = [entry["idx"] for entry in new["entries"]]
    if (
        len(set(tags)) != len(tags)
        or any(type(index) is not int or index < 0 for index in indices)
        or any(right <= left for left, right in zip(indices, indices[1:], strict=False))
    ):
        raise RuntimeError(
            "Migration journal has duplicate identities or invalid indices"
        )
    # Drizzle chooses the next filename from the last index, not array length.
    # Preserve the published prefix exactly while respecting historical gaps.
    for entry in new["entries"][len(prefix) :]:
        if entry["idx"] != int(entry["tag"].split("_", 1)[0]):
            raise RuntimeError("New migration index must match its filename prefix")
    if set(tags) != {
        path.stem
        for path in Path("migrations").glob("*.sql")
        if re.fullmatch(r"[0-9]+_.+", path.stem)
    }:
        raise RuntimeError("Migration journal and SQL inventory differ")
    return {
        "published_entries": len(prefix),
        "candidate_entries": len(tags),
        "published_sql_sha256": hashes,
    }


def validate_native_ci_input(workflow, tested_base, variable_base=None):
    job = re.search(
        r"(?ms)^  native-images:\n(.*?)(?=^  [a-zA-Z0-9_-]+:\n|\Z)", workflow
    )
    if not job or "./.github/workflows/container-check.yml" not in job[1]:
        raise RuntimeError(
            "This recipe requires CI-owned native verification; review changed workflow ownership"
        )
    uses_variable = bool(
        re.search(
            r"node_base_image:\s*\$\{\{\s*vars\.CONTAINER_NODE_BASE_IMAGE\s*}}", job[1]
        )
    )
    if uses_variable and variable_base != tested_base:
        raise RuntimeError(
            "Manual CI passes a stale repository Node-base variable to native verification. "
            "Pass the checked-in images-packaging Node base through a source-derived job output; "
            "preserve the repository variable, publication approval gates and all four native jobs."
        )
    return {"owner": "ci.yml", "repository_variable_used": uses_variable}


def check_native_ci_input():
    tested = json.loads(
        Path("scripts/ci/test-suites/images-packaging.json").read_text()
    )["prepare"]["defaultEnv"]["NODE_BASE_IMAGE"]
    variable = api(f"repos/{REPOSITORY}/actions/variables/CONTAINER_NODE_BASE_IMAGE")[
        "value"
    ]
    return validate_native_ci_input(
        Path(".github/workflows/ci.yml").read_text(), tested, variable
    )


def main():
    inputs = json.loads(Path(os.environ["MAINTAIN_INPUTS_FILE"]).read_text())
    stage = os.environ["MAINTAIN_CHECK_STAGE"]
    sha = os.environ["MAINTAIN_SOURCE_SHA"]
    subprocess.run(
        ["git", "diff", "--check", inputs["upstream_sha"] + "...HEAD"], check=True
    )
    subprocess.run(["node", "scripts/ci/run-tests.mjs", "audit"], check=True)
    details = {
        "scope": "Diff and canonical suite-registration audit only. Dependency-backed workspace/static and runtime checks are required in hosted CI."
    }
    if stage == "integration" and inputs["starting_integration"]:
        details["migration_prefix"] = check_prefix(inputs["starting_integration"])
    if stage == "integration":
        if inputs["fork"] != f"https://github.com/{REPOSITORY}.git":
            raise RuntimeError("CI preflight is restricted to the reviewed OCE fork")
        details["native_ci_input"] = check_native_ci_input()
    destination = Path(os.environ["MAINTAIN_CHECK_STATE_DIR"]) / "receipt.json"
    destination.write_text(
        json.dumps({"source_sha": sha, "details": details}, indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
