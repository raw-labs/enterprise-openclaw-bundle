# Maintain the OCE candidate

This project owns the OCE composition recipe and verification policy. OCE owns
product code, combined tests and candidate commits. Bundle definitions and release
qualification remain separate; this project never selects a bundle version.

Install the Python Maintain CLI and authenticated Codex and GitHub CLIs. Use Node
24+ and Python 3.11+. Review and commit recipe changes on a bundle branch before
planning. Run from this directory:

```sh
maintain validate
maintain plan
maintain build RUN_ID
maintain report RUN_ID
maintain publish-candidate RUN_ID
maintain qualify RUN_ID
maintain report RUN_ID
```

The current pilot ends after qualification: **no promotion, tags or releases**.
Feature publication is disabled. The published integration and main are protected
by exact frozen-ref checks. Adding a feature uses `maintain feature add ID --pr URL
--intent TEXT`, followed by recipe review/commit and a new plan. IDs identify
features in constraints and reports. Explicit `requires`/`after` constrain order;
otherwise Maintain inspects interactions and records its proposed order.

The control ledger is `codex/maintain-records` in this repository. It records
recipe commit, exact inputs, actual generated code refs, decisions, order and
check receipts. Ignored `.maintain/` contains local SQLite, workspaces and raw logs.
`maintain recover RUN_ID` restores a remotely checkpointed run; `resume` continues
local construction and `qualify` continues hosted qualification. Retained object
branches and a run-specific candidate live in the OCE fork. Source PRs stay intact.

Local checks prove diff/suite-registration structure and published migration-prefix integrity. Historical journal gaps are valid: published entries stay exact, and each new index matches its filename prefix so Drizzle generates the next migration safely;
they are not runtime qualification. The catalog check measures the exact migration
SQL with PostgreSQL 18.6 and the pinned Drizzle implementation, then measures a real
dump/restore for the complete schema and every migration prefix, followed by actual SQL upgrades of each restored prefix. Exact measured mixed catalogs remain separate from fresh/fully restored catalogs; guard and grant checks stay mandatory. Incremental and
fresh final catalogs must agree; measuring a prefix does not admit it into the
production migration policy. Its isolated `codex/maintain/oce/RUN/catalog/INPUTS-METHOD` probe adds
only the frozen measurement harness on a separate branch. It uses the existing
manual Full Integration workflow identity with a probe-only job; it never changes
the candidate workflow or publishes images. Only that run's disposable database
and volume are removed. Measured schema-input and method digests bind safe receipts;
metadata-only repair can reuse the measurement, while changed SQL requires another.
The guard refuses guessed/mismatched completed, ledger or restore catalogs.
Canonical guarded migration and upgrade tests remain required on the final candidate.

Dependency-backed workspace, formatting and
static checks remain mandatory in canonical hosted CI. Hosted source checks dispatch CI, CodeQL and the pinned Storybook build
once per exact candidate, validate the full canonical CI aggregate and small lane
receipts, and require the named combined scenarios without skips. The same-source
Storybook artifact supports separate browser inspection and screenshot/video capture;
a successful build alone is not visual proof. Manual CI already invokes the
nonpublishing native container workflow. The native check reuses that exact CI run,
requires all four native image jobs, and reads bounded `platform.json` entries from
their OCI artifacts. It requires the same CI attempt and checked-in Node base; no
second native workflow is dispatched. The local preflight refuses the known stale
repository-variable input without changing variables or publication approval gates.
No images are published. Dispatch intentions survive local interruption; uncertain responses are
reconciled against exact-SHA remote runs before another action. Failure logs stay
local and reports contain safe identities, counts, URLs and receipt digests.

Generic regressions belong in their OCE feature; combination regressions belong in
the OCE candidate and existing suite manifests. `prompts/` owns contextual worker
guidance. `checks/` owns orchestration and evidence validation, not product behavior.
None of this proves live Slack/Teams messages, public Teams ingress, model turns,
customer installations or a shipping bundle.

If a committed check itself is wrong, stop the completed build, commit the corrected
recipe, and run `maintain revalidate OLD_RUN --reason TEXT`, then build the new run.
This retains exact selected inputs and generated code, preserves the old recipe
and results, and reruns checks. Changed intent, prompts or selection need a new plan.
