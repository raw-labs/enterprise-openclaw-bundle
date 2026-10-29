"""Structural source audit and published migration-prefix guard, not runtime proof."""

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path


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
    if len(set(tags)) != len(tags) or [e["idx"] for e in new["entries"]] != list(
        range(len(tags))
    ):
        raise RuntimeError(
            "Migration journal has duplicate identities or invalid indices"
        )
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
    destination = Path(os.environ["MAINTAIN_CHECK_STATE_DIR"]) / "receipt.json"
    destination.write_text(
        json.dumps({"source_sha": sha, "details": details}, indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
