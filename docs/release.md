# Select, build and release

Release JSON owns exact sources, digests, inventories and evidence. New stock
candidates use our selected fork checkpoint and start without shipping images.
The recorded pilot remains available through the legacy commands; its evidence
never qualifies a new build. See [versions and distribution](distribution.md).

## Prepare and verify

Use Python 3.12+, Git, Node 24.16+ and Helm 3. Select a new, agreed prerelease
identity. Export exact Git objects, never working-tree content. An explicit
read-only local object repository may accelerate the export.

```bash
python3 scripts/stock.py new --id <agreed-prerelease> --output .work/candidate.json
python3 scripts/stock.py --selection .work/candidate.json source --output .work/source
python3 scripts/stock.py --selection .work/candidate.json dependencies --output .work/renderer-dependencies
python3 scripts/bundle.py --release .work/candidate.json package \
  --source .work/source --dependencies .work/renderer-dependencies --output dist/bundle.tar.gz
```

This produces an unbuilt review bundle. It cannot install through the delivered
tool. The deterministic archive contains the unchanged chart and upstream MIT
notice, exact selection, hashed file manifest, renderer with its locked public
suffix dependencies and their notices, installation helper, optional defaults and
static procedures. Build contexts, notice-layer fragment, image exports, credentials
and private test logs stay outside the SE archive.

Validation CI exports both the historical pilot source and the selected fork,
checks negative inputs and inventories, reproduces archives, verifies delivered
files and renders both profiles with the real chart. Those checks establish
packaging compatibility, not runtime qualification.

## Native shipping artifacts

The manually dispatched private `build.yml` workflow takes the agreed release
identity. It uses existing Depot runner labels for native AMD64 and ARM64; it
creates no runner, cloud or installation resources. Both jobs export all three
roles from the selected source recipes. A tracked notice-only stage preserves
OCE's MIT license in each final image; it changes no Codex code or identity.
Build timestamps use the selected commit epoch. Apt and other dependency execution
can still change image bytes; rebuilds need not reproduce old image digests.
Registry publication is disabled by default. Run the build and checks first and
obtain explicit authorization for the private GHCR destination before publication.
Use `publish.yml` with that successful build's run ID to copy its existing exports;
it validates the trusted main run and receipts and performs no image rebuild.

Before installing test dependencies, the build verifies the complete source
inventory. Native checks bind each export manifest to its loaded config ID, source
label, architecture and license. The controller startup test, four unchanged
runtime startup/broker/worker test files, runtime repository-volume test and
credential isolation tests execute against the actual shipping exports. Credential
isolation uses the actual service and a separate source-built test-only client.
No test identity patch, skipped test, emulation or unconfined fallback is accepted.

The selected source prepares a temporary k3d fixture, derives its reviewed Codex
seccomp additions from that node baseline, and uses its bounded job-owned AppArmor
policy where Docker enables AppArmor. Owned fixture cleanup and policy removal run
on success or failure. Temporary CI fixtures are not customer deployments. Raw TAP
stays in ignored private files; only sanitized counts, identities, confinement
artifacts and log checksums enter the candidate record. Customer node policy still
requires review and installation tests.

## Private candidate publication

Only after both native jobs succeed does a separate job receive `packages: write`.
It checks the private bundle repository, expected package ownership/visibility,
all native receipts and every destination tag before writing. An existing tag must
match the exact tested index; it is reused without a registry write. Unknown
authentication or tag state stops publication. It assembles one OCI index per role
from the exact two tested manifests, copies with digest preservation, and verifies
the private published index digest. It never builds replacement shipping images.

The resulting candidate stays unqualified pending review. Its exact images,
both native receipts, per-platform policy artifacts and SE bundle are retained as
private Actions artifacts. Partial publication must be inspected before any retry;
never overwrite a tag to repair it. The workflow does not create a GitHub Release
or promote a stable version automatically.

Review the final digests, confinement and test scope before customer handoff.
Model/provider access and customer infrastructure acceptance are separate from
these native export checks. An owner-reviewed JSON acceptance record must bind
the exact image references, source commits, Codex version, both native receipt
hashes and both confinement profiles. Use `stock.py accept --review <record>
--output <new-release-selection>` with the built candidate as `--selection`.
The command preserves the source inventory and receipts and refuses to replace
existing evidence. Neither build nor publication CI calls it. The delivered tool
verifies the same review record; customer qualification remains false.
Stable version promotion is a separate release-owner decision.

Preserve published history. Before pushing source or creating a release, verify
identity, origin, private visibility and the expected remote head. Deliver through
private releases or approved channels. Mirror all platforms with
`skopeo copy --all --preserve-digests`, verify destination manifests and record the
mirror map; never put build or presales credentials in a customer installation.
