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

## Check changes

With Git, Python 3.12+, Node 24+ and Bash:

```bash
python3 scripts/check.py
```

For packaging checks, also use Helm 3 and the Go version pinned in
[scripts/cli.py](scripts/cli.py). Use a new output directory. Resolving a retained
upgrade baseline requires authenticated GitHub CLI access and `GH_TOKEN`.
Supply the token through the environment and keep it out of shell traces.
For GitHub npm packages, the token also needs package read access.

```bash
export GOTOOLCHAIN="$(PYTHONPATH=scripts python3 -c 'from cli import GO_VERSION; print(GO_VERSION)')"
OUT=.work/resolved
python3 scripts/release.py resolve --output "$OUT"
python3 scripts/cli.py build --selection "$OUT/candidate.json" \
  --source "$OUT/source" --output "$OUT/cli"
python3 scripts/check.py --integration --selection "$OUT/candidate.json"
```

Pass `--definition FILE` to select a version, `--from-git CHECKOUT` to read
the pinned OCE commit from a local repository, or `--dependency-cache DIR` and
`--plugin-cache DIR` to use verified tarballs.

A maintainer reviews changes before merging. A sole maintainer may review
their own changes, subject to GitHub rules. For packaging changes, inspect the
extracted archive. Follow the [release procedure](docs/contributing/release.md)
to qualify and publish.
