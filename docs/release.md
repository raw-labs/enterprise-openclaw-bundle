# Build a bundle

For maintainers. Each `bundles/<version>/bundle.json` is the human-authored release
selection. Its version is independent of the OCE chart version. Retain hash-pinned
ingredients used by maintained definitions; add a new file when changing one.
Published source and definitions remain available at their immutable Git tags.

The definition selects the exact OCE commit, compatible OpenClaw commit and Codex
version, both architectures, optional preset templates, bundled plugin IDs and the
Codex installation profile. Its `build` section selects optional hash-pinned source
patches and reviewed confinement inputs. Runtime versions and plugin IDs must match
the selected source Dockerfiles after applying those patches. The build code adds
mandatory license notices. Presets are included for optional import; they are not
created in a running installation. Connections and live Agent configuration are
outside this milestone.

Installation examples live in `docs/examples/installations/`. They are shipped
with the documentation and checked by the renderer. Customer-specific settings
belong in the customer's private deployment repository.

Commit the definition and ingredients, then run **Release bundle** on main and
select its definition path. Publication defaults to enabled. From the CLI:

```bash
gh workflow run release.yml --ref main -f definition="$BUNDLE_DEFINITION" -f publish=true
```

The single Action resolves Git sources and locked renderer dependencies, generates
a file inventory, builds three images on native AMD64 and ARM64 Depot runners,
runs the selected source's controller, runtime and credential isolation tests with
confinement and no skips, and assembles their exact tested manifests. It then
publishes private GHCR indexes, verifies a reproducible customer archive and real
chart renders for the documentation examples, and creates the immutable tag and
private GitHub prerelease.
Generated definitions, digests, receipts, checksums and provenance are release assets;
there is no manual checkpoint or acceptance JSON to prepare or commit.

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
