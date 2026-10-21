# Publish source, releases and images

The intended distribution is one public source repository with public GitHub
release downloads and public GHCR images. Keep all three private until the owner
explicitly authorizes the visibility change. Preparation, reviews and non-publishing
checks may proceed. Do not change a live installation as part of publication.

## Prepare while private

- Review the source tree, retained Git refs, releases, Actions logs/artifacts and
  image contents for credentials or customer data. Investigate scanner findings;
  revoke an exposed credential before targeted cleanup. Non-secret historical
  registry identifiers alone do not require rewriting history.
- Preserve upstream notices, immutable tags, release assets and image digests.
  Retain historical private distribution records as evidence of how they were
  built; do not rewrite them when access changes.
- Run contributor and prepared-source packaging checks. Exercise workflow guards
  for both repository visibilities, including fork/PR rejection and destination
  visibility mismatches. New builds still require native evidence.
- Review live branch/tag protections against `.github/policies/`. Keep secret
  scanning, push protection and read-only default workflow permissions enabled.

## Owner-authorized visibility change

Recheck identity, canonical origin, expected main head and the clearance inventory
immediately before proceeding. Changing repository visibility also exposes retained
release downloads and Actions logs/artifacts; there is no separate private setting
for a published release inside a public repository. See [GitHub visibility
consequences](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/managing-repository-settings/setting-repository-visibility).

Change the three existing GHCR packages to public and the repository to public
within the authorized transition. Package visibility is independent of repository
visibility; [making a package public cannot be reversed](https://docs.github.com/en/packages/learn-github-packages/configuring-a-packages-access-control-and-visibility). Preserve every digest and
tag. Avoid dispatching a publishing workflow while repository/package visibility
is mixed: its checks deliberately reject that state.

Enable private vulnerability reporting and verify maintainers can receive reports.
Require approval for workflows from all outside collaborators, then confirm the
branch/tag protections, secret scanning and token defaults still apply. Verify
anonymous source access, release downloads and all image indexes/platform
manifests against retained checksums and digests. Publication needs no new version,
new repository, history rewrite or live installation update.

## Public CI

Fork pull requests run offline contributor checks on GitHub-hosted runners without
package credentials. Integration runs only on canonical main pushes. Native builds
run only on canonical manual dispatches: main, or reviewed `codex/` branches with
publication disabled. Only main can publish. Paid runners never execute fork PR
code, and `pull_request_target` is not used.

CI derives distribution visibility from the actual repository and verifies it
again through the API before publishing. Every existing image package must match;
a public destination must already exist. CI never changes visibility settings.
Public Actions logs and ordinary build artifacts are public material. Raw failure
diagnostics are uploaded only while the repository is private; after publication,
reproduce failures in a protected maintainer environment when those logs are
needed. Customer inputs, credentials and live installation state must never enter
release CI. See [release](release.md), [distribution](distribution.md) and
[security reporting](../SECURITY.md).
