# Develop the bundle factory

Start with the [component map](docs/overview.md) and [bundle schema](docs/bundle-schema.md).
Change factory behavior here. Product behavior belongs in OCE; provider integration
behavior belongs in its plugin repository. Customer infrastructure and credentials
belong outside this repository.

Follow the [review responsibilities](docs/maintainers.md). Report suspected
vulnerabilities through the [private security procedure](SECURITY.md).

## Fast checks

From a fresh checkout, with Git, Python 3.12+, Node 24+ and Bash:

```bash
python3 scripts/check.py
```

This checks maintained definitions and their ingredient hashes, Python/JavaScript
syntax, repository documentation links and unit rejection tests. It needs no
network, credentials, Helm, Go, Docker or prepared `.work/` directory. Synthetic
validator inputs never qualify a shipping artifact.

Pull requests use this credential-free check on GitHub-hosted runners. Credentialed
packaging checks are restricted to pushes to the private canonical main branch;
forks and public-repository runs do not receive package credentials or paid runners.

## Packaging integration

Also install Helm 3 and Go. Use the toolchain selected by the factory; CI pins
Node, Helm and Go in the [validation workflow](.github/workflows/validate.yml).
Python dependencies are standard-library only. Public release-asset selections
download without credentials. A selection using GitHub's npm registry instead
requires `GH_TOKEN` with package read access; supply it through protected credential
tooling, never source or shell transcripts.

Choose an empty output directory. The resolver exports exact committed OCE source,
applies pinned patches and verifies package downloads; it does not build images or
create a release. Omitting `--definition` selects the highest maintained definition.

```bash
export GOTOOLCHAIN="$(PYTHONPATH=scripts python3 -c 'from cli import GO_VERSION; print(GO_VERSION)')"
python3 scripts/release.py resolve --output .work/resolved
python3 scripts/cli.py build --selection .work/resolved/candidate.json \
  --source .work/resolved/source --output .work/resolved/cli
python3 scripts/check.py --integration --selection .work/resolved/candidate.json
```

Integration checks require all inputs and fail if they are missing. They test real
chart rendering, deterministic package assembly, matched CLI binaries and rejection
of changed source, packages and image selections. They do not grant installation or
runtime qualification. No tests are silently skipped.

For an existing OCE Git checkout, add `--from-git /absolute/path/to/checkout` to
`resolve`; only the selected commit is read, not uncommitted changes. Verified local
tarballs may be supplied with `--dependency-cache DIRECTORY` and `--plugin-cache
DIRECTORY`. Their hashes and identities are still checked. An alternative output
directory works with `--selection DIRECTORY/candidate.json`.

## Make a change

Keep only maintained definitions and their referenced ingredients on the working
branch. Retired releases are reproduced from their original tags. Start a new
definition before changing published ingredients; never replace historical receipts
or reuse published versions. Local drafts remain unqualified.

Put Agent templates in `presets/`, installation profiles in `profiles/`, and
release-specific source patches beside their definition. The definition owns the
selection and hashes; directory names do not select defaults. Preserve original
license notices in patches and packaged code.

The factory rejects curated templates that enable browser, experimental UI or
optional channels, bypass human Coding approvals, or grant wildcard/network escape
access. Review changes to this policy as security changes. Installation owners
may explicitly enable capabilities in their own copied Configuration; the factory
policy is not an administrator-enforced ceiling on live Agents.

Submit original contributions under Apache-2.0. Identify borrowed or adapted
material and retain its existing copyright and license notices; do not replace
upstream notices with RAW attribution. See the [license scope](THIRD_PARTY_NOTICES.md).

For a behavior change, include the relevant rejection or integration coverage and
update its short procedure. Run fast checks for every change and packaging checks
when changing resolution, package contents, templates, profiles or delivery docs.
Report which checks ran; local packaging does not substitute for native qualification.
Publication remains a separate [maintainer operation](docs/release.md).

Keep site inputs, Secret exports, raw credential-bearing logs and generated records
out of commits. `.work/` is private scratch space; `dist/` is disposable packaging
output, not a source of release authority. Use the selected release assets for handoff.
