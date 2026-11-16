# Bundle definition

Edit `bundles/<version>/bundle.json` to select what ships. Use schema version
`6` for new definitions. When copying a schema 5 definition, remove
`build.upgradeFrom` and use the [release workflow input](release.md). Reproduce
older formats from their release tags.

| Field | Selects |
| --- | --- |
| `schemaVersion` | Definition format version |
| `version` | Folder name and release tag, using a numbered `alpha`, `beta`, or `rc` |
| `oce` | HTTPS GitHub repository URL and full commit |
| `openclawCommit`, `codexVersion` | Must match the OpenClaw commit and Codex version in OCE's runtime recipe |
| `architectures` | `linux/amd64` and `linux/arm64` |
| `plugins` | Plugin IDs from the runtime recipe or pinned package objects |
| `presets` | `includeDefaults` and hash-pinned `files` using OCE's preset format |
| `codexProfile` | Hash-pinned Codex installation profile in OCE's format |
| `build.patches` | Ordered hash-pinned source patches; may be empty |
| `build.confinement` | Hashes of OCE's seccomp generator, its implementation if split, and the CI AppArmor policy |

A file reference has a repository-relative `path` and a `sha256` hash. To
include a preset from `presets/` or a profile from `profiles/`, reference it
in the definition.

A plugin package uses `id`, `package`, `version`, tarball `sha256`, and a
`source` object with `repository` and `commit`. Supply `url` for a public
GitHub release asset. Without it, the Action needs access to the GitHub npm
package. The build checks identity, license and runtime API compatibility.

See the [validator](../../scripts/release.py) for exact constraints. Change
ingredients with a new bundle version. To change the format, update the
validator, consumers, rejection tests and this guide together.
