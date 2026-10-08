# RAW Labs enterprise OpenClaw bundle

Private build and release source. Customer installations consume versioned bundles
and digest-pinned images; their infrastructure, credentials and state stay in
separate private installation repositories.

- [Release records](releases/): source pins, image digests, qualification and artifact inventories.
- [Build checkpoint](releases/source-checkpoint.json): input for new candidates.
- [Build workflow](.github/workflows/build.yml): native builds and checks.
- [Publication workflow](.github/workflows/publish.yml): publish existing checked exports.
- [Validation workflow](.github/workflows/validate.yml): release-input and packaging checks.
- [SE installation procedure](docs/install.md): delivered artifact entry point.
- [Release procedure](docs/release.md): package, build, qualify and distribute.
- [Versions and distribution](docs/distribution.md): prereleases, private registry and customer delivery.
- [Scope and ownership](docs/scope.md): bundle and installation responsibilities.
