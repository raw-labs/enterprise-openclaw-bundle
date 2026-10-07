# Select, package and release

Use Python 3.12+, Git, Node 24+ and Helm 3 for packaging; Docker Buildx and the
selected upstream dependencies are additional build/qualification requirements.
The release JSON and its hashed source-file inventory are authoritative. Fetch
exact source objects; a local object database is an explicit read-only acceleration,
not a requirement or a source of working-tree content.

```bash
python3 scripts/bundle.py --release releases/pilot-baseline.json validate
python3 scripts/bundle.py --release releases/pilot-baseline.json source \
  --output .work/source
# Optional: --from-git /absolute/path/to/selected-source-object-repository
python3 scripts/bundle.py --release releases/pilot-baseline.json package \
  --source .work/source --output dist/bundle.tar.gz
python3 -m unittest discover -s tests -v
```

Expect a deterministic archive/checksum containing the unchanged chart, release
selection, manifest, installation tool, upstream renderer/bootstrap helper, optional
presets, example inputs, seccomp/provenance, procedures and notices. No images,
source trees, private build overlay, credentials or installation state are embedded.
The same inputs produce the same archive bytes. Artifact checks establish packaging,
not image availability or execution.

## Build a new candidate

Choose a new release identity. Existing image references become inherited inputs;
only successful pushed build outputs replace all three. No command promotes a
candidate automatically or rewrites historical evidence.

```bash
python3 scripts/bundle.py --release releases/pilot-baseline.json candidate \
  --id evaluation-001 --output .work/candidate.json
python3 scripts/bundle.py --release .work/candidate.json build \
  --source .work/source --output .work/build
```

Local builds load AMD64 images and retain unqualified metadata. Full builds need
substantial local capacity/network access; emulation is not runtime qualification.
For private publication, authenticate Docker to the selected ECR registry and
publish to a new output directory:

```bash
python3 scripts/bundle.py --release .work/candidate.json build \
  --source .work/source --output .work/published --push \
  --registry-prefix '<account>.dkr.ecr.<region>.amazonaws.com/<prefix>'
```

The CLI verifies AWS account, existing private repositories, immutable tags without
exclusions, and absent release tags. It creates no cloud resources. Builder access
must cover the three repositories; node read access is separately granted.
Do not retry partial publication with the same identity until all tags are inspected.

Controller uses selected OCE's root Dockerfile runtime target. Runtime uses its
pinned OC recipe and bridge patches, then the tracked Codex overlay with the
newly built base digest. Credential service reuses OCE's service target; its pilot
image was built by the installation's equivalent supplemental Dockerfile. Runtime
inventory helper equality was established against the selected source; builds
use that source helper. Package lock, plugin metadata, dedicated command and
provenance must resolve the same Codex version. Base images and downloads are
pinned, but apt/dependency execution can change output; rebuilds are not promised
to reproduce old image digests.

## Check and qualify

```bash
python3 scripts/bundle.py --release releases/pilot-baseline.json check-images \
  --output .work/baseline-image-identity.json
python3 scripts/bundle.py --release .work/published/candidate.json qualify \
  --source .work/source --seccomp profiles/codex-seccomp.json \
  --output .work/qualification
```

`check-images` pulls exact digests and checks architecture, source labels and runtime
provenance/version. The pilot credential image may lack a source label; its recorded
digest does not manufacture one. A failure is retained and blocks acceptance.
`qualify` requires native Linux AMD64 Docker, source inventory, reviewed seccomp,
installed dependencies and real upstream production/runtime/repository-volume tests and credential service isolation
against the actual service digest (with locally built test-only client/fixture images).
The tracked patch raises only the source's Codex identity expectation to the overlay
version; this is adapted qualification, not stock upstream proof. No lower version,
skip, unconfined run or old pilot receipt is accepted. Raw TAP stays private/ignored
because fixtures may contain synthetic credentials. The sanitized receipt records
exact images, sources, confinement, patch and counts. It does not establish real
model/provider/repository workflows or qualify customer infrastructure.

After reviewing successful evidence, the release owner creates a new `kind: release`
selection with `qualification.status: qualified`, a relative receipt path and
`receiptSha256`. Record `customerQualified` accurately; customer acceptance is
separate. Validation verifies receipt identities/inputs and requires nonzero tests,
all passing without skips. The baseline's `pilot-recorded` state is never promoted.

## Private automation and delivery

Validation runs without cloud credentials. The manually dispatched image workflow
is restricted to private repository `main` and a protected `release-build` environment.
Configure that environment with `AWS_ROLE_ARN`, `AWS_REGION`, `ECR_PREFIX` and review
protection. Use short-lived OIDC credentials with trust restricted to this repository
and environment; grant only identity/read and push access to the three existing
repositories. No static AWS keys, production deployment or automatic GitHub Release
publication is configured. Candidate metadata is retained as a private Actions
artifact; publishing remains an explicit release-owner step.

For customer mirroring, an authorized delivery operator uses Skopeo with separately
protected source/destination registry authentication:

```bash
skopeo copy --all --preserve-digests --authfile /secure/registry-auth.json \
  docker://<source-role-reference-from-release.json> \
  docker://<private-customer-repository>:<unique-release-id>
skopeo inspect --raw --authfile /secure/registry-auth.json \
  docker://<private-customer-repository>:<unique-release-id> | shasum -a 256
```

Repeat for all three roles; require manifest hashes equal selected digests and
record destination digest references in `mirrors.json`. Verify destination ownership,
private visibility and tag absence/immutability before copying; stop on mismatches
or uncertain outcomes. Grant pull access to both node pools and test actual pulls.
A digest-preserving mirror does not require new image qualification; changed bytes do.

After checking repository privacy, create a private versioned GitHub Release or use
an authorized private artifact channel to deliver the archive/checksum and optional
mirror map. Source repository collaborators may download private GitHub Release
assets; customers without that access receive the exported archive through the
approved channel. Bundle membership does not grant ECR access. Do not make the
repository, artifacts or source images public to simplify delivery.

The next OCE integration input is an exact combined commit, its chosen OC pin/archive
checksum, matching chart version, recipes/bridge patches, compatible overlay decision
and version-aware qualification fixtures. Regenerate the source archive/file inventory
from that exact commit, review profile/default compatibility, update pins in a new
candidate and build/qualify all roles. Keep upstream topic PRs independent.
