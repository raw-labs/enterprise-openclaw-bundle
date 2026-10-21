# Bundle ownership

Own release selection, reusable build/packaging, verification and customer handoff.
Read other repositories without changing them. Do not deploy infrastructure, change
live Agents. Native plugin packages are selected and verified as build ingredients;
provider credentials and account setup belong to installation owners.

`bundles/<version>/bundle.json` owns human-authored ingredient selection,
optional source patches and reviewed confinement inputs. `presets/` owns Agent
templates; `profiles/` owns installation profiles. `scripts/` owns factory mechanics;
`delivery/` owns the small payload
for package verification and OCE input preparation. Product operations belong to
OCE; infrastructure and installation settings belong to installation owners.
The release Action generates inventories, native receipts, image indexes, archives
and provenance only as CI artifacts and GitHub release assets. `docs/` owns short
static procedures and installation examples. README is navigation only.
Preserve published source and evidence at immutable Git tags and release assets.
Do not duplicate current pins, fleet identities or qualification claims in prose.
Keep documentation short and static; use Git history for ordinary chronology.
Keep only maintained definitions and their ingredients on the working branch;
reproduce retired releases from their original tags. Source layout changes need
a new unqualified definition, never edits to a published definition.

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
