# RAW Labs enterprise OpenClaw bundle

Private build and release source. Customer installations consume versioned bundles
and digest-pinned images; their infrastructure, credentials and state stay in
separate private installation repositories.

- [Release records](releases/): source pins, image digests, qualification and artifact inventories.
- [Build checkpoint](inputs/source-checkpoint.json): input for new candidates.
- [Build workflow](.github/workflows/build.yml): native builds and checks.
- [Publication workflow](.github/workflows/publish.yml): publish existing checked exports.
- [Validation workflow](.github/workflows/validate.yml): release-input and packaging checks.
- [Installation procedure](docs/install.md): sales engineers and installation operators.
- [Operations procedure](docs/operate.md): acceptance, diagnosis, upgrades and recovery.
- [Release procedure](docs/release.md): bundle maintainers selecting, building and publishing.
- [Distribution procedure](docs/distribution.md): maintainers and sales engineers arranging access and mirrors.
