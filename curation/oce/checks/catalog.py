"""Measure new SQL catalogs on an isolated hosted probe, without editing candidate code.

The probe ref contains only the candidate plus this frozen control-recipe harness.
It never qualifies the application; exact-candidate canonical CI remains required.
"""

import hashlib
import json
import os
import re
import subprocess
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

SCHEMA_PATHS = [
    "migrations",
    "scripts/migration-catalog.mjs",
    "packages/occ/package.json",
    "pnpm-lock.yaml",
    "pnpm-workspace.yaml",
    "package.json",
    "compose.postgres.yaml",
]
MANIFEST = "migrations/meta/_canonical-history.json"


def fingerprint():
    rows = command(
        ["git", "ls-tree", "-r", "--full-tree", "HEAD", "--", *SCHEMA_PATHS]
    ).splitlines()
    rows = sorted(row for row in rows if row.split("\t", 1)[1] != MANIFEST)
    return hashlib.sha256(("\n".join(rows) + "\n").encode()).hexdigest()


def validate_measurement(value, schema, method):
    if value.get("schema_digest") != schema or value.get("method_digest") != method:
        raise RuntimeError(
            "Catalog measurement belongs to different schema inputs or method"
        )
    for key in ("completed_catalog", "ledger_catalog", "restored_catalog"):
        if not re.fullmatch("[0-9a-f]{64}", value.get(key, "")):
            raise RuntimeError("Catalog measurement lacks an actual PostgreSQL digest")
    count = value.get("migration_count")
    prefixes = value.get("prefixes", {})
    if (
        not isinstance(count, int)
        or isinstance(count, bool)
        or not 1 <= count <= 512
        or not isinstance(prefixes, dict)
        or set(prefixes) != {str(index) for index in range(1, count + 1)}
    ):
        raise RuntimeError("Catalog measurement lacks complete migration prefixes")
    for prefix in prefixes.values():
        if not isinstance(prefix, dict) or any(
            not re.fullmatch("[0-9a-f]{64}", prefix.get(key, ""))
            for key in ("catalog", "ledger", "restored_catalog")
        ):
            raise RuntimeError(
                "Catalog prefix lacks actual native/restore measurements"
            )
    final = prefixes[str(count)]
    if (final["catalog"], final["ledger"], final["restored_catalog"]) != (
        value["completed_catalog"],
        value["ledger_catalog"],
        value["restored_catalog"],
    ):
        raise RuntimeError(
            "Final migration prefix differs from fresh catalog measurement"
        )
    if (
        not value.get("postgresql", "").startswith("18.6")
        or value.get("drizzle") != "0.45.4"
    ):
        raise RuntimeError("Catalog measurement used unexpected pinned dependencies")
    if (
        not re.fullmatch("[0-9a-f]{40}", value.get("probe_sha", ""))
        or not str(value.get("run_id", "")).isdigit()
    ):
        raise RuntimeError("Catalog measurement lacks hosted source/run identity")


def measure(inputs, state, schema, method, helper, workflow):
    source = os.environ["MAINTAIN_SOURCE_SHA"]
    branch = (
        f"codex/maintain/oce/{inputs['run_id']}/catalog/{schema[:16]}-{method[:16]}"
    )
    probe = state / "probe"
    if not probe.exists():
        probe.mkdir()
        command(["git", "init", "--quiet", str(probe)])

    def git(*args, env=None):
        result = subprocess.run(
            ["git", "-C", str(probe), *args], env=env, capture_output=True, text=True
        )
        if result.returncode:
            raise RuntimeError(
                "Owned catalog probe Git operation failed: " + result.stderr[-2000:]
            )
        return result.stdout.strip()

    git("config", "credential.helper", "")
    git("config", "user.name", "Miguel Branco")
    git("config", "user.email", "miguel@raw-labs.com")
    git("fetch", "--no-tags", "--", str(Path.cwd()), source)
    marker = probe / ".git/maintain-catalog-source"
    if not marker.exists():
        git("checkout", "--detach", source)
        (probe / ".maintain-catalog-probe.mjs").write_bytes(helper)
        (probe / ".github/workflows/full-integration.yml").write_bytes(workflow)
        save(
            probe / ".maintain-catalog-inputs.json",
            {
                "schema_digest": schema,
                "method_digest": method,
                "source_sha": source,
            },
        )
        git(
            "add",
            "--",
            ".maintain-catalog-probe.mjs",
            ".maintain-catalog-inputs.json",
            ".github/workflows/full-integration.yml",
        )
        timestamp = git("show", "-s", "--format=%ct", source)
        git(
            "commit",
            "--quiet",
            "-m",
            "Measure candidate migration catalogs in disposable PostgreSQL",
            env={
                **os.environ,
                "GIT_AUTHOR_DATE": "@" + timestamp + " +0000",
                "GIT_COMMITTER_DATE": "@" + timestamp + " +0000",
            },
        )
        marker.write_text(source)
    elif marker.read_text() != source or git("status", "--porcelain"):
        raise RuntimeError("Owned catalog probe has unexpected changes")
    sha = git("rev-parse", "HEAD")
    ref = "refs/heads/" + branch
    transport = [
        "-c",
        "credential.helper=",
        "-c",
        "credential.helper=!gh auth git-credential",
    ]
    location = inputs["fork"]
    found = git(*transport, "ls-remote", "--refs", location, ref).split()
    if found and found[0] != sha:
        raise RuntimeError("Catalog probe ref changed unexpectedly")
    save(
        state / "probe-intention.json",
        {"source_sha": source, "probe_sha": sha, "branch": branch},
    )
    if not found:
        git(*transport, "push", "--", location, f"{sha}:{ref}")
    run = workflow_run("full-integration.yml", sha, branch, state)
    run = wait_runs([run], sha, state)[0]
    artifacts = [
        a
        for a in pages(
            f"repos/{REPOSITORY}/actions/runs/{run['id']}/artifacts", "artifacts"
        )
        if a["name"] == "catalog-measurement" and not a["expired"]
    ]
    if len(artifacts) != 1:
        raise RuntimeError("Catalog probe must emit one unique measurement artifact")
    entries = artifact_json(
        artifacts[0], lambda name: Path(name).name == "catalog-measurement.json"
    )
    if len(entries) != 1:
        raise RuntimeError("Catalog probe artifact lacks one measurement")
    value = entries[0][1]
    validate_measurement(value, schema, method)
    if (
        value["probe_sha"] != sha
        or str(value["run_id"]) != str(run["id"])
        or value["source_sha"] != source
    ):
        raise RuntimeError("Catalog receipt source/run mismatch")
    value["run_url"] = run["html_url"]
    save(state / "measurement.json", value)
    return value


def main():
    inputs = json.loads(Path(os.environ["MAINTAIN_INPUTS_FILE"]).read_text())
    if (
        inputs["fork"] != f"https://github.com/{REPOSITORY}.git"
        or api("user")["login"] != "miguelbranco80"
    ):
        raise RuntimeError(
            "Catalog testing is restricted to the reviewed fork and owner"
        )
    for kind in ("GIT_AUTHOR_IDENT", "GIT_COMMITTER_IDENT"):
        if (
            command(["git", "var", kind]).split(">", 1)[0]
            != "Miguel Branco <miguel@raw-labs.com"
        ):
            raise RuntimeError("Unexpected Git author/committer for catalog probe")
    root = Path(__file__).resolve().parent
    helper, workflow = (
        (root / "catalog-probe.mjs").read_bytes(),
        (root / "catalog-workflow.yml").read_bytes(),
    )
    method = hashlib.sha256(helper + b"\0" + workflow).hexdigest()
    schema = fingerprint()
    state = Path(os.environ["MAINTAIN_CHECK_STATE_DIR"])
    value = None
    if (state / "measurement.json").exists():
        value = json.loads((state / "measurement.json").read_text())
    else:
        for prior in inputs.get("prior_check_evidence", []):
            measured = prior.get("evidence", {}).get("details", {}).get("measurement")
            if (
                measured
                and measured.get("schema_digest") == schema
                and measured.get("method_digest") == method
            ):
                value = measured
                break
    if value is None:
        value = measure(inputs, state, schema, method, helper, workflow)
    validate_measurement(value, schema, method)
    save(
        state / "receipt.json",
        {
            "source_sha": os.environ["MAINTAIN_SOURCE_SHA"],
            "details": {"measurement": value},
        },
    )
    manifest = json.loads(Path(MANIFEST).read_text())
    valid = (
        manifest["catalogs"]["completed"] == value["completed_catalog"]
        and manifest["ledgerCatalogs"]["completed"] == value["ledger_catalog"]
        and manifest["logicalRestoreCatalogs"].get(value["completed_catalog"])
        == value["restored_catalog"]
    )
    if not valid:
        print(json.dumps(value, indent=2))
        raise RuntimeError(
            "Canonical catalog metadata differs from the measured PostgreSQL result. Update only measured completed/ledger/logical-restore digests, retain prior catalog history, then rerun. This measurement does not replace guarded upgrade and application CI."
        )
    print(
        "Canonical completed catalog and logical restore match real PostgreSQL measurements."
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(
            "Catalog check transport failed; resume the saved probe"
            if isinstance(error, OSError)
            else str(error),
            file=sys.stderr,
        )
        raise SystemExit(1) from None
