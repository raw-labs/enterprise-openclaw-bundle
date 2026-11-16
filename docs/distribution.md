# Download and verify a bundle

Choose a [release](https://github.com/raw-labs/enterprise-openclaw-bundle/releases).
Save a reviewed `bundle.lock.json` in the installation repository. Copy the tag
and the `bundleCommit` and `artifactSha256` from the release's `provenance.json`.

```json
{
  "repository": "raw-labs/enterprise-openclaw-bundle",
  "tag": "<release tag>",
  "commit": "<bundleCommit>",
  "archive": "bundle.tar.gz",
  "sha256": "<artifactSha256>"
}
```

Use Python 3.12+ and an authenticated GitHub CLI. Set `FETCH` to the path to
[fetch.py](../delivery/fetch.py) from a reviewed source revision, and `SITE` to
the protected installation directory.

```bash
BUNDLE=$(python3 "$FETCH" fetch --lock "$SITE/bundle.lock.json" \
  --cache "$SITE/bundle-cache") && cd "$BUNDLE"
```

Open `INSTALL.md` or `UPDATE.md`. To use an archive downloaded separately,
add `--archive FILE`. To reuse a cache offline, run `verify` with the same lock
and cache before invoking bundled tools.

Kubernetes pulls images separately using `metadata/release.json`. Public GHCR
images allow anonymous pulls. For a mirror, copy both architectures and preserve
the index digests; pass the mirror map during rendering.
