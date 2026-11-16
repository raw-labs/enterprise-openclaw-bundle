# Download a bundle

1. Open the [releases page](https://github.com/raw-labs/enterprise-openclaw-bundle/releases)
   and choose the version you want. Under **Assets**, download `bundle.tar.gz` and
   `bundle.tar.gz.sha256` into the same directory.
2. In that directory, check the download.

   ```bash
   shasum -a 256 -c bundle.tar.gz.sha256
   ```

   On Linux you can also use `sha256sum -c bundle.tar.gz.sha256`. Continue only
   if the check reports `bundle.tar.gz: OK`.

3. Extract the archive.

   ```bash
   tar -xzf bundle.tar.gz
   ```

   Open the folder named after the release tag. Start with `INSTALL.md` for a new
   installation or `UPDATE.md` for an upgrade.

## Automate downloads

For repeatable runs, save a reviewed `bundle.lock.json` in your installation
repository. Download `provenance.json` from the same release and copy its
`version`, `bundleCommit`, and `artifactSha256` into these three fields.

```json
{
  "repository": "raw-labs/enterprise-openclaw-bundle",
  "tag": "<version>",
  "commit": "<bundleCommit>",
  "archive": "bundle.tar.gz",
  "sha256": "<artifactSha256>"
}
```

Save [`fetch.py`](../delivery/fetch.py) from a reviewed source revision next to
the lock file. From that directory, run this with Python 3.12+ and an
authenticated GitHub CLI.

```bash
python3 fetch.py fetch --lock bundle.lock.json --cache bundle-cache
```

The command prints the path to the verified, extracted bundle. For a download
you already have, add `--archive bundle.tar.gz`. To recheck an extracted cache
offline, run the same command with `verify` in place of `fetch` and omit
`--archive`.

## Container images

Kubernetes pulls the images listed in `metadata/release.json` separately. Public
GHCR images can be pulled anonymously. If you use a mirror, copy both
architectures, preserve the image index digests, and pass the mirror map when
rendering the installation inputs.
