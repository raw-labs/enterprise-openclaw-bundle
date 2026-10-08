# Versions and distribution

Bundle versions are independent of the upstream chart version. Use immutable
SemVer prerelease tags with numbered `alpha`, `beta` or `rc` suffixes. Alpha denotes
early artifact preparation, beta denotes evaluation, and an RC is intended for
final acceptance. A prerelease label does not confer qualification. Create a stable
version only after reviewing qualification of the final artifacts. Never reuse a
tag, replace a published asset or move published history.

Private GHCR is the distribution registry for new bundle images. Record repository
names and final digests in the release selection. Presales needs authorized GitHub
package access, without an AWS account. Outside Actions, private GHCR pulls require
a classic GitHub token with `read:packages` and any required organization SSO
authorization. CI publication uses the repository's short-lived `GITHUB_TOKEN`.
Link packages to the private bundle repository and verify their private visibility
and access settings. Reject existing tags; GHCR tags themselves are mutable, so
installations always select verified digests. Keep registry credentials out of
artifacts, examples and Git.

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

Build and qualify both native Linux AMD64 and ARM64 images. Keep source CI evidence,
shipping artifact qualification and customer installation acceptance distinct.
The source checkpoint record is a preparation input, not an installable release.
The release procedure identifies the build path implemented by the current tools.

References: [GHCR authentication and digests](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry),
[package permissions](https://docs.github.com/en/packages/learn-github-packages/configuring-a-packages-access-control-and-visibility),
[release asset limits](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases).
