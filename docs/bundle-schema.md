# Bundle definition

For maintainers selecting ingredients or extending the build system.
`bundles/<version>/bundle.json` uses our bundle-definition schema. Its validator is
[`definition()` in scripts/release.py](../scripts/release.py); resolution checks
that the selected source actually supports those ingredients.

## Supported fields

All fields below are required. Unknown top-level fields and unknown `build` fields
are rejected.

| Field | Meaning and constraints |
| --- | --- |
| `schemaVersion` | Definition format version. The current validator accepts `2`. |
| `version` | Bundle release version, matching its folder. Accepted form: `vMAJOR.MINOR.PATCH-alpha.N`, `-beta.N` or `-rc.N`, with a positive sequence number. Stable versions are not yet supported by the Action. |
| `oce` | `repository`: HTTPS GitHub Git URL; `commit`: full 40-character commit hash. The source supplies the controller, chart, runtime Dockerfiles and tests. |
| `openclawCommit` | Full 40-character OpenClaw commit hash. Must match the runtime Dockerfile after source patches. |
| `codexVersion` | Three-part Codex version. Must match the runtime Dockerfile after source patches. |
| `architectures` | Exactly `["linux/amd64", "linux/arm64"]`; both native builds and checks are required. |
| `plugins` | Nonempty ordered list of unique bundled OpenClaw plugin IDs, using lowercase letters, digits and hyphens, starting with a letter. Must match both the Dockerfile's build selection and retained extensions, including order. |
| `presets` | List of file references to optional OCE preset templates. May be empty. Each filename must end in `-preset.json` and be unique. Live Agent plugin settings must be empty. |
| `codexProfile` | File reference to the selected Codex installation profile, using OCE's profile format. The preparation tool passes it explicitly to the renderer; original upstream profiles remain available. |
| `build.patches` | Ordered list of file references to Git patches. May be empty. Applied to the exported OCE source before compatibility checks, inventory and builds. Must preserve the upstream license. |
| `build.confinement` | SHA-256 hashes of the selected source's `scripts/lib/codex-seccomp-profile.mjs` and `.github/actions/run-ci-lane/codex-sandbox.apparmor`. Checked after patches; changed policies require review and new hashes. |

A file reference has exactly `path` and `sha256`: a repository-relative path and
the lowercase SHA-256 of its exact bytes. References cannot escape the repository. Commit the
referenced files with the definition. Preset contents and installation profiles
use OCE's formats; `bundle.json` selects them rather than defining their schemas.

Mandatory license handling belongs in build code. Installation examples belong in
`docs/examples/installations/`; they are included and rendered during packaging.
Image digests, inventories, receipts and provenance are generated outputs.
Customer settings and credentials belong in the customer's private installation.

## Adding plugins

`plugins` currently checks the source's plugin selection; it is not a package
installer. Adding a name to this list alone fails resolution if the Dockerfile
does not build and retain it.

To add a plugin supported by OpenClaw's existing build, select a compatible OCE
commit or supply a hash-pinned source patch that updates the runtime Dockerfile's
build selection and retained extensions. Update `plugins` to match. Use a new
bundle version and run both native builds and checks, including a functional check
for the added plugin. Shipping plugin code does not configure its credentials,
Connections or customer access.

Installing arbitrary third-party plugins from a registry or Git repository is not
implemented. When needed, extend the schema and build code together: define exact
source/version and integrity pins, deterministic installation, license handling,
generated provenance and native verification. Add this support when an ingredient
requires it; do not predeclare unused fields.

## Evolving the schema

`version` identifies a release; `schemaVersion` identifies how to read its definition.
Changing ingredients under the same format needs a new bundle version, not a new
schema version. Keep definitions for maintained versions and retain their pinned
files; published definitions and build code remain available at immutable Git tags.

When adding or changing a field or its meaning, update the validator, resolver,
build/packaging code, rejection tests and this guide together. Bump `schemaVersion`
when older validators cannot correctly interpret the definition. Reject unsupported
versions explicitly. Support older formats deliberately if they remain maintained;
otherwise reproduce their releases from their original tags. Never reinterpret or
rewrite a published definition. Every newly built artifact needs its own checks.
