# RAW Labs enterprise OpenClaw bundle

Private build and release source. Customer installations consume versioned bundles
and digest-pinned images; their infrastructure, credentials and state stay in
separate private installation repositories.

- [Recorded pilot baseline](releases/pilot-baseline.json): preserved sources, images and evidence.
- [Alpha release selection](releases/v0.1.0-alpha.1.json): shipping digests and native review scope.
- [Alpha artifact record](releases/v0.1.0-alpha.1-artifact.json): bundle checksum and delivered file verification.
- [Alpha build input](releases/v0.1.0-alpha.1-input.json): exact selected fork and stock build inputs.
- [Source checkpoint](releases/source-checkpoint.json): next input and source evidence.
- [SE installation procedure](docs/install.md): delivered artifact entry point.
- [Release procedure](docs/release.md): package, build, qualify and distribute.
- [Versions and distribution](docs/distribution.md): prereleases, private registry and customer delivery.
- [Scope and ownership](docs/scope.md): supported boundaries and next integration input.

Run `python3 scripts/bundle.py --release releases/v0.1.0-alpha.1-input.json validate`.
