# Work on the bundle

| Path | Purpose |
| --- | --- |
| `bundles/<version>/` | Release definition, patches and notes |
| `presets/`, `profiles/` | Agent templates and installation profiles |
| `scripts/`, `tests/` | Build, package and verify releases |
| `delivery/` | Download and prepare the kit |
| `docs/` | Installation, operations and contributor guides |

OCE owns product behavior. Installation owners provide infrastructure, site
settings and credentials. See the [bundle definition](docs/contributing/bundle-schema.md).
Preserve upstream licenses and published tags. Keep generated evidence, site
configuration and credentials out of commits.

## Run the local checks

Use Git, Python 3.12+, Node 24+, and Bash.

```bash
python3 scripts/check.py
```

## Check the package

Install Helm 3 and the Go version listed in [scripts/cli.py](scripts/cli.py).
If the Go command selects a different toolchain, set `GOTOOLCHAIN` to that pinned
version. Choose an output directory that does not exist yet.

For a published upgrade baseline, authenticate the GitHub CLI and set
`GH_TOKEN` in your environment. If you use GitHub npm packages, the token also
needs package read access.

```bash
OUT=.work/resolved
python3 scripts/release.py resolve --output "$OUT"
python3 scripts/cli.py build --selection "$OUT/candidate.json" \
  --source "$OUT/source" --output "$OUT/cli"
python3 scripts/check.py --integration --selection "$OUT/candidate.json"
```

Pass `--definition FILE` to select a version, `--from-git CHECKOUT` to read
the pinned OCE commit from a local repository, or `--dependency-cache DIR` and
`--plugin-cache DIR` to use verified tarballs.

## Review and release

A maintainer reviews changes before merging. A sole maintainer may review
their own changes, subject to GitHub rules. For packaging changes, inspect the
extracted archive. Follow the [release procedure](docs/contributing/release.md)
to qualify and publish.
