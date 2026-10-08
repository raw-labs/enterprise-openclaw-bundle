# Build a bundle

For maintainers. Each `bundles/<version>/bundle.json` is the human-authored release
selection. Its version is independent of the OCE chart version. Retain hash-pinned
ingredients used by maintained definitions; add a new file when changing one.
Published source and definitions remain available at their immutable Git tags.

See the [bundle schema](bundle-schema.md) for supported fields, source compatibility
checks and adding plugins. Presets are shipped for optional import. Connections
and live Agent configuration are outside this milestone.

Installation examples live in `docs/examples/installations/`. They are shipped
with the documentation and checked by the renderer. Customer-specific settings
belong in the customer's private deployment repository.

Commit the definition and ingredients, then run **Release bundle** on main and
select its definition path. The Action runs on demand; pushing a commit or tag does
not start a release. Publication defaults to enabled. Set `BUNDLE_DEFINITION` to
the chosen `bundles/<version>/bundle.json` path, then run:

```bash
gh workflow run release.yml --ref main -f definition="$BUNDLE_DEFINITION" -f publish=true
```

The single Action resolves Git sources and locked renderer dependencies, generates
a file inventory, builds three images on native AMD64 and ARM64 Depot runners,
runs the selected source's controller, runtime and credential isolation tests with
confinement and no skips, and assembles their exact tested manifests. It verifies
the archive and real chart renders before publishing private GHCR indexes, checks
the published handoff again, then creates the immutable tag and private prerelease.

## Generated outputs

Publication produces three multiarchitecture images: controller, runtime and
repository credentials. Each has AMD64 and ARM64 manifests. The customer archive
contains the chart, installer, templates, examples, license notices and verification
records; images are pulled separately.

The GitHub release has ten attachments:

- `bundle.tar.gz` and `bundle.tar.gz.sha256`: customer handoff and checksum.
- `bundle.json`: a copy of the chosen definition.
- `resolved.json` and `source-files.json`: resolved ingredients and source inventory.
- `release.json` and `publication.json`: final image selection and publication record.
- Two `<version>-native-<architecture>-receipt.json` files: native test evidence.
- `provenance.json`: build commit/run, definition hash and output checksums.

Actions also retains four temporary artifact collections: resolved build inputs,
native AMD64 exports, native ARM64 exports and release outputs. No generated records
are committed to the source repository.

## Checks and retries

Set `publish=false` for the same native build and packaging checks without registry
writes or a tag/release. Its review archive is marked unpublished and installation
admission rejects it. Local packaging checks can resolve without native builds:

```bash
python3 scripts/release.py resolve --definition "$BUNDLE_DEFINITION" --output .work/resolved
python3 -m unittest discover -s tests -v
```

A published version cannot be rebuilt or replaced. For a failed publishing job,
use GitHub's **Re-run failed jobs** while its original resolved inputs and native
exports remain available. Different existing image digests are rejected. If a draft
release or partial publication remains, inspect it before recovery; never delete or
replace published history to make a retry succeed. New ingredients require a new
version. Stable promotion remains a separate release-owner decision.

Native artifact checks do not qualify provider access or a customer installation.
Operators follow the delivered installation and acceptance procedures. Build inputs,
OCI exports and private raw test logs stay out of the customer configuration archive.
See [distribution](distribution.md) for private access and mirror policy.
