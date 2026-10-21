# Versions and distribution

For release maintainers and sales engineers arranging artifact access or customer
mirrors. Installation operators use the access handoff with the delivered install guide.

Download `bundle.tar.gz` and `bundle.tar.gz.sha256` from the selected
GitHub release. While the repository is private, use authorized GitHub CLI access
and an empty download directory:

```bash
: "${VERSION:?Set VERSION to the selected bundle tag}"
: "${DOWNLOAD:?Set DOWNLOAD to an absolute empty download directory}"
gh release download "$VERSION" --repo raw-labs/enterprise-openclaw-bundle \
  --pattern 'bundle.tar.gz*' --dir "$DOWNLOAD"
```

After the owner makes the repository public, download the same two assets without
credentials from the selected release page, or use:

```bash
curl --fail --location --output "$DOWNLOAD/bundle.tar.gz" \
  "https://github.com/raw-labs/enterprise-openclaw-bundle/releases/download/$VERSION/bundle.tar.gz"
curl --fail --location --output "$DOWNLOAD/bundle.tar.gz.sha256" \
  "https://github.com/raw-labs/enterprise-openclaw-bundle/releases/download/$VERSION/bundle.tar.gz.sha256"
```

In that directory, verify with `sha256sum -c bundle.tar.gz.sha256` (macOS:
`shasum -a 256 -c bundle.tar.gz.sha256`), extract with `tar -xzf bundle.tar.gz`,
and enter the extracted version directory. Start with its `INSTALL.md`.
Other release assets provide provenance and test evidence.

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

The intended public distribution includes source, release downloads and all three
image packages. Keep them private until the owner authorizes the transition.
Package visibility is configured independently from repository visibility. The
factory checks that both match before publishing; it does not change settings.
Reuse an existing tag only when its index matches exactly; reject a different or
unverifiable tag. Installations select verified digests. Keep registry credentials
out of artifacts, examples and Git.

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
