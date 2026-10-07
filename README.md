# RAW Labs enterprise OpenClaw bundle

Private build and release source. Customer installations consume versioned bundles
and digest-pinned images; their infrastructure, credentials and state stay in
separate private installation repositories.

- [Selected baseline](releases/pilot-baseline.json): sources, images, dependencies and evidence.
- [SE installation procedure](docs/install.md): delivered artifact entry point.
- [Release procedure](docs/release.md): package, build, qualify and distribute.
- [Scope and ownership](docs/scope.md): supported boundaries and next integration input.

Run `python3 scripts/bundle.py --release releases/pilot-baseline.json validate`.
