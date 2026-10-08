# Bundle ownership

Own release selection, reusable build/packaging, verification and customer handoff.
Read other repositories without changing them. Do not deploy infrastructure, change
live Agents, or add OpenClaw Connections in this milestone.

`bundles/<version>/bundle.json` owns human-authored ingredient selection;
`recipes/` owns hash-pinned build additions and reviewed confinement inputs.
The release Action generates inventories, native receipts, image indexes, archives
and provenance as CI artifacts and GitHub release assets. `releases/` retains
previously published evidence unchanged. `defaults/` and `profiles/` own selectable
templates and examples; retain old hash-pinned ingredients when adding new ones.
`scripts/` owns mechanics; `docs/` owns short static procedures. README is navigation only.
Do not duplicate current pins, fleet identities or qualification claims in prose.
Keep documentation short and static; use Git history for ordinary chronology.

Use exact source commits, digest images and verified file inventories. Never alter
historical evidence or apply an untracked qualification replacement. New builds
start unqualified. Check negative release inputs, source/image mismatch rejection,
artifact contents, reproducibility and real chart rendering. Runtime qualification
requires native target hardware, reviewed confinement and no skipped tests.
Mocked checks and pilot receipts never qualify new builds or customer installations.

Never commit credentials, customer account IDs, domains, state, plans, Secret
exports or raw credential-bearing test logs. Keep build inputs
out of SE archives; preserve upstream license notices in charts and runtime images.
Distribute through private releases/registries or authorized customer mirrors.
Before pushing, verify identity, repository privacy, origin and expected remote head.
Preserve published history. Stop on an unexpected destination or head.
