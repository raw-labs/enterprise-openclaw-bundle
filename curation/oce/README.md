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

Local checks prove source/suite structure and published migration-prefix integrity;
they are not runtime qualification. Hosted source checks dispatch CI and CodeQL
once per exact candidate, validate the full canonical CI aggregate and small lane
receipts, and require the named combined scenarios without skips. Native checks
then dispatch only `container-check.yml`, require all four native image jobs and
read bounded `platform.json` entries from their OCI artifacts. No images are
published. Dispatch intentions survive local interruption; uncertain responses are
reconciled against exact-SHA remote runs before another action. Failure logs stay
local and reports contain safe identities, counts, URLs and receipt digests.

Generic regressions belong in their OCE feature; combination regressions belong in
the OCE candidate and existing suite manifests. `prompts/` owns contextual worker
guidance. `checks/` owns orchestration and evidence validation, not product behavior.
None of this proves live Slack/Teams messages, public Teams ingress, model turns,
customer installations or a shipping bundle.
