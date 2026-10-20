# Bundle definition

For maintainers selecting ingredients or extending the build system.
`bundles/<version>/bundle.json` uses our bundle-definition schema. Its validator is
[`definition()` in scripts/release.py](../scripts/release.py); resolution checks
that the selected source actually supports those ingredients.

## Supported fields

Top-level fields and `build.patches`/`build.confinement` are required;
`build.upgradeFrom` is optional. Unknown fields are rejected.

| Field | Meaning and constraints |
| --- | --- |
| `schemaVersion` | Definition format version: `2`–`5`. Version `3` installs presets and native packages; `4` explicitly selects upstream default seeding; `5` also accepts Codex prereleases and a retained upgrade-test baseline. |
| `version` | Bundle release version, matching its folder. Accepted form: `vMAJOR.MINOR.PATCH-alpha.N`, `-beta.N` or `-rc.N`, with a positive sequence number. Stable versions are not yet supported by the Action. |
| `oce` | `repository`: HTTPS GitHub Git URL; `commit`: full 40-character commit hash. The source supplies the controller, chart, runtime Dockerfiles and tests. |
| `openclawCommit` | Full 40-character OpenClaw commit hash. Must match the runtime Dockerfile after source patches. |
| `codexVersion` | Exact three-part Codex version; schema `5` also accepts `-alpha.N`, `-beta.N` and `-rc.N`. Must match the runtime Dockerfile after source patches. |
| `architectures` | Exactly `["linux/amd64", "linux/arm64"]`; both native builds and checks are required. |
| `plugins` | Nonempty ordered list of unique native plugin selections. String IDs must match OCE's build/retention lists. Versions `3`–`5` also accept pinned package objects. |
| `presets` | Versions `4`/`5`: `{ "includeDefaults": false, "files": [...] }`, using OCE's native seeding fields. `files` contains file references; names and filenames are unique and filenames end in `-preset.json`. Versions `2`/`3` use a list and retain their original behavior. Versions `3`–`5` install files in the controller and prepare their image paths. Agent plugin policy stays empty; native plugin settings use Configuration values. Enabled native plugins must be selected for the runtime. |
| `codexProfile` | File reference to the selected Codex installation profile, using OCE's profile format. The preparation tool passes it explicitly to the renderer; original upstream profiles remain available. |
| `build.patches` | Ordered list of file references to Git patches. May be empty. Applied to the exported OCE source before compatibility checks, inventory and builds. Must preserve the upstream license. |
| `build.confinement` | SHA-256 hashes of the selected source's `scripts/lib/codex-seccomp-profile.mjs` and CI AppArmor policy (`scripts/ci/codex-bwrap.apparmor`, or the historical `.github/actions/run-ci-lane/codex-sandbox.apparmor`). Checked after patches; changed policies require review and new hashes. |
| `build.upgradeFrom` | Optional in schema `5`: immutable published bundle version used for retained-state qualification. The Action verifies its tag, archive and provenance, tests Connections state across native runtime replacement and upgrades its installed controller through the packaged OCE helper. This input stays out of the customer archive. |

A file reference has exactly `path` and `sha256`: a repository-relative path and
the lowercase SHA-256 of its exact bytes. References cannot escape the repository. Commit the
referenced files with the definition. Preset contents and installation profiles
use OCE's formats; `bundle.json` selects them rather than defining their schemas.

Mandatory license handling belongs in build code. Installation examples belong in
`docs/examples/installations/`; they are included and rendered during packaging.
Image digests, inventories, receipts and provenance are generated outputs.
Customer settings and credentials belong in the customer's private installation.

## Native plugins and presets

A string in `plugins` selects an extension already built by the OCE runtime recipe.
For an additional RAW package, use a version `3`–`5` package object with exactly:

- `id`: native OpenClaw plugin ID.
- `package`: scoped `@raw-labs/...` npm package name.
- `version`: exact package version.
- `sha256`: SHA-256 of the published tarball.
- `source`: `repository` HTTPS Git URL and full `commit` used to publish it.

The Action downloads the package from GitHub's private npm registry using its
job token. Grant the factory repository **Read** in the package's **Manage Actions
access** settings. Resolution rejects changed bytes, wrong package identities,
missing notices, links and unsafe archive paths. Native builds embed the compiled
package without fetching dependencies at runtime, check its SDK identity, and
record its file inventory and source pins in generated provenance.

Shipping a plugin makes its code available. OCE native Configuration values,
Secret bindings, tool policy and UI consent still control its use; provider
accounts and grants belong to the installation owner. Added plugins require
functional checks against both actual native shipping images.

Selected preset files use OCE's existing seeding. They are included once under
`oce/deploy/presets/raw/` for inspection and at the matching controller image path.
No installer import command is needed. OCE adds missing presets and preserves
existing same-name copies; a new bundle does not overwrite operator edits or
reconcile preset removals. Version `2` retains its original archive-only behavior.

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
