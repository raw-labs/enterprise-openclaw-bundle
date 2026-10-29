# Reconstruct the OCE candidate

Inspect the previous integration through refs/maintain/previous, especially its
scripts/integration/selection.json compatibility decisions and combined tests.
Reassess them against current upstream and all selected features; do not blindly
replay old patches or preserve retired implementation. Compare the resulting code
with the previous integration and explain upstream changes, refreshed features,
removed obsolete adapters and new interaction fixes separately in your report.

The published persistence prefix now includes all 62 old migrations. Preserve
EVERY existing journal entry, SQL identity and SQL bytes; append upstream and
feature evolution after the prefix. Preserve previous snapshot validity, native
role use, assigning-session and outbound/embedded invariants. Extend the existing
real PostgreSQL populated upgrade coverage through supported migrator/application
roles. Update the canonical migration catalog/history for the actual resulting
schema; never invent a catalog hash or merely change an expected hash to pass.
This explicit user requirement takes precedence over generic instructions to
discard development compatibility. No migrations may be rewritten or renumbered.

Keep Slack AND Teams, dedicated AND embedded, OpenClaw AND Codex Harness behavior.
Retain exact callback resource ownership and serving authority. Extend owning
combined API/worker/Kubernetes tests for interactions, denials and lifecycle
cleanup. Retain the three existing real provisioning scenarios and both provider
cutovers, guarded native Teams transport, actual pinned Chromium AND WebKit Teams
directory engines, role/session authority and migration compatibility. Add a
regression only for changed behavior or a discovered gap, not for each merge.
Register required coverage in the existing canonical suite manifests. Do not
replace real SDK/database/cluster execution with self-fulfilling mocks.

Review old CI host/AppArmor and Docker archive import adaptations against current
upstream. Preserve actual sandbox, seccomp, source/config/native-architecture and
receipt checks. Use existing approved fork runner variables/compatibility labels
if upstream defaults are unavailable; do not change repository variables or weaken
containment. CI, CodeQL and nonpublishing container-check must remain manually
dispatchable on the candidate ref. Do not add release or publication actions.

Recipes, selection lists and run reports belong in the control repository. Remove
obsolete engine-only scripts/integration tracking from the new product tree if
present, but retain current product documentation, source-backed flow history and
Manual Notes. Do not re-add a new maintenance manifest to OCE. Keep RFC identities
unique without changing historical proposal status. Preserve the current upstream
runtime source/recipe pins unless a selected feature explicitly needs a reviewed
adaptation; report any such difference and qualify exact final native images.
