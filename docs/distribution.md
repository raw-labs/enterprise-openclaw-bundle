# Versions and distribution

For release maintainers and sales engineers arranging artifact access or customer
mirrors. Installation operators use the access handoff with the delivered install guide.

Keep a reviewed `bundle.lock.json` in the site repository. Copy the release tag
and the `bundleCommit` and `artifactSha256` from its `provenance.json`.

```json
{
  "repository": "raw-labs/enterprise-openclaw-bundle",
  "tag": "<release tag>",
  "commit": "<bundleCommit>",
  "archive": "bundle.tar.gz",
  "sha256": "<artifactSha256>"
}
```

Use Python 3.12+ and GitHub CLI access. Run [fetch.py](../delivery/fetch.py)
from a reviewed source revision. Set `SITE` to the protected site directory and
`FETCH` to the path to that script.

```bash
BUNDLE=$(python3 "$FETCH" fetch --lock "$SITE/bundle.lock.json" \
  --cache "$SITE/bundle-cache") && cd "$BUNDLE"
```

Open `INSTALL.md` or `UPDATE.md` in the verified archive. For an offline
archive, add `--archive FILE`. For offline cache reuse, run `verify` with the
same lock and cache before running bundled tools.

Bundle versions are independent of the upstream chart version. Use immutable
SemVer prerelease tags with numbered `alpha`, `beta` or `rc` suffixes. Alpha denotes
early artifact preparation, beta denotes evaluation, and an RC is intended for
final acceptance. A prerelease label does not confer qualification. The Action
currently publishes prereleases only; stable promotion needs explicit implementation
and review of the final artifacts. Never reuse a tag, replace a published asset or
move published history.

GHCR hosts the bundle images. The release asset `release.json` and the archive's
`metadata/release.json` record exact repository names and index/platform digests.
Public GHCR images support anonymous pulls; no GitHub token or image pull Secret
is needed for those images. While packages remain private, authorized pulls need
a classic GitHub token with `read:packages` and any required organization SSO
authorization. CI publication uses its short-lived `GITHUB_TOKEN` in either mode.

Customer installations use their own authorized registry and pull identities:
ECR for AWS, ACR for Azure, or an on-prem registry such as Harbor. Registry choice
does not establish tested support for that customer's cluster. Copy all manifests
and platforms with digest preservation, verify destination digests, and record the
mirror map. Do not place a presales employee's GitHub token in a customer cluster.

For disconnected delivery, export verified OCI image archives separately from
the SE configuration/chart bundle. Include checksums and an image inventory with
the index and both platform digests. Verify the imported manifests and actual
node pulls before installation acceptance. Release assets larger than GitHub's
per-file limit need an approved private delivery channel.

References: [GHCR authentication and digests](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry),
[package permissions](https://docs.github.com/en/packages/learn-github-packages/configuring-a-packages-access-control-and-visibility),
[release asset limits](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases).
