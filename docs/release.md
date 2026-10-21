# Build a bundle

For maintainers. Each `bundles/<version>/bundle.json` is the human-authored release
selection. Its version is independent of the OCE chart version. Retain hash-pinned
ingredients used by maintained definitions; add a new file when changing one.
Published source and definitions remain available at their immutable Git tags.
The working branch contains maintained definitions only. A draft definition is not
a published release; local validation does not create a tag, release or image publication.

See the [bundle schema](bundle-schema.md) for supported fields, source compatibility
checks and adding native plugins. Selected presets are installed through OCE's
seeding; packaged plugins are embedded in the runtime. Provider accounts, secrets
and live Agent configuration belong to the installation owner.

Installation examples live in `docs/examples/installations/`. They are shipped
with the documentation and checked by the renderer. Customer settings belong in the installation owner's protected workspace.

Commit the definition and ingredients, then run **Release bundle** on main and
select its definition path. The Action runs on demand; pushing a commit or tag does
not start a release. Publication defaults to disabled. Set `BUNDLE_DEFINITION` to
the chosen `bundles/<version>/bundle.json` path, then run:

```bash
gh workflow run release.yml --ref main -f definition="$BUNDLE_DEFINITION" -f publish=true
```

The single Action resolves Git sources and locked renderer dependencies, generates
a file inventory, builds unchanged `occ` from that same source for macOS/Linux
AMD64/ARM64 and runs its CLI tests. Native AMD64 and ARM64 Depot runners check the
Linux executables and build three images, then run the selected source's controller,
runtime and credential isolation tests with confinement and no skips. It also runs
OCE's image-identity and controller/broker compatibility probe on both native
targets using locally staged OCI indexes containing the exact built manifests.
The native receipts bind that proof to the exports. When `build.upgradeFrom` is
selected, both targets also check retained Connections state from that published
runtime; the installation check installs the previous package, preserves its
edited presets and upgrades the controller/database through the packaged OCE
helper. These checks do not prove a running Agent fleet rollout or provider access.
The Action assembles the tested manifests
and verifies the archive and real chart renders before publishing GHCR indexes, checks
the published handoff again, installs the extracted package on disposable k3d
with PostgreSQL TLS and checks authenticated `occ` access, then creates the
immutable tag and prerelease. Repository visibility controls release access; image
packages must match that visibility. CI never changes either setting. Raw failure
diagnostics are uploaded only while the repository is private.

## Generated outputs

Publication produces three multiarchitecture images: controller, runtime and
repository credentials. Each has AMD64 and ARM64 manifests. The customer archive
contains the chart, matched `occ` binaries, input preparation tool, upstream
installation/upgrade helpers, templates, examples, notices and release metadata;
images are pulled separately.

The GitHub release has eleven attachments:

- `bundle.tar.gz` and `bundle.tar.gz.sha256`: customer handoff and checksum.
- `bundle.json`: a copy of the chosen definition.
- `resolved.json` and `source-files.json`: resolved ingredients and source inventory.
- `release.json` and `publication.json`: final image selection and publication record.
- Two `<version>-native-<architecture>-receipt.json` files: native test evidence.
- `installation-receipt.json`: extracted-package installation and authenticated CLI check on disposable k3d infrastructure.
- `provenance.json`: build commit/run, definition hash and output checksums.

The archive starts with `INSTALL.md`, `UPDATE.md`, `OPERATE.md`, `SUPPORT.md`,
`SECURITY.md` and a short operator-facing `AGENTS.md`.
Its commands are `bin/occ` and `bin/prepare`; packaged OCE files are
under `oce/`, with supporting code under `lib/` and release metadata under
`metadata/`. Native receipts remain separate release assets.

The factory requires a new handoff directory and enforces this exact attachment
allowlist. Before installation checks it expects ten files; the installation
receipt brings the final set to eleven. Extra, missing, linked or non-regular
assets are rejected, even if an extra file is added to provenance. Publication
uploads explicit allowed filenames; release notes are created outside the asset
directory. Asset checks verify inventory consistency, not a signature or attestation.

Actions also retains four temporary artifact collections: resolved build inputs,
native AMD64 exports, native ARM64 exports and release outputs. No generated records
are committed to the source repository.

## Checks and retries

Integration checks run only after canonical main pushes. Pull requests run the
offline contributor check without package credentials. Native release jobs require
manual dispatch in the canonical repository; publishing requires main. These
boundaries apply with either private or public visibility. CI sets
`BUNDLE_DISTRIBUTION_VISIBILITY` from repository visibility and rejects a mismatched
live destination or image package. Public packages must already exist. Visibility
changes require the owner's separate [public transition](public-readiness.md).

Maintainers may manually dispatch `release.yml` at a reviewed `codex/` branch with
`publish=false` to test unmerged factory changes. This runs both native targets and
a separate handoff-review job with read-only repository/package permissions. It
uploads review artifacts (visible to repository readers) and creates no registry publication, tag or release.
The publishing handoff job remains restricted to main. Review branch changes and
check the exact remote head and expected repository visibility before dispatch.

Set `publish=false` for the same native build and packaging checks without registry
writes or a tag/release. Its review archive is marked unpublished and installation
admission rejects it. Local packaging checks can resolve without native builds. Follow
[contributor setup](../CONTRIBUTING.md) for prerequisites, package authentication,
the selected Go toolchain, fast checks and prepared-source integration checks.

A published version cannot be rebuilt or replaced. For a failed publishing job,
use GitHub's **Re-run failed jobs** while its original resolved inputs and native
exports remain available. Different existing image digests are rejected. If a draft
release or partial publication remains, inspect it before recovery; never delete or
replace published history to make a retry succeed. New ingredients require a new
version. Stable promotion remains a separate release-owner decision.

Native artifact checks do not qualify provider access or a customer installation.
Operators follow the delivered installation and acceptance procedures. Build inputs,
OCI exports and private raw test logs stay out of the customer configuration archive.
See [distribution](distribution.md) for access and mirror policy.
