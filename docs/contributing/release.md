# Build a release

1. Add a [definition](bundle-schema.md) under `bundles/<version>/`. Use a new
   version for changes to published artifacts.
2. Add `NOTES.md` beside it with the changes operators need to know and any
   required action. The same notes appear in the archive and GitHub release.
3. Run [contributor checks](../../CONTRIBUTING.md). Verify the archive contents
   and operator instructions.

Set `BUNDLE_DEFINITION` to the path to the new definition. Start **Release bundle**
on demand; a commit or tag does not start it.

```bash
gh workflow run release.yml --ref main -f definition="$BUNDLE_DEFINITION" -f publish=false
```

Use `publish=false` for a review build on main or a reviewed `codex/` branch.
The review archive cannot be installed through normal bundle tooling.
To publish, verify identity, origin, repository visibility and exact remote
head, then dispatch main with `publish=true`. GHCR package visibility must
match the repository. CI does not change visibility or deploy installations.

The Action checks both native architectures and rehearses installation before
publishing the image indexes and GitHub prerelease. If the definition selects
an upgrade baseline, the Action checks that path too. The customer downloads
are `bundle.tar.gz` and its checksum. Inspect provenance and the receipts for
the exact scope of the checks.

Use **Re-run failed jobs** while the original inputs and exports are still
available and main has not moved. Inspect partial publication before retrying.
Published tags, assets and digests are immutable. See
[download and image access](../distribution.md) for the customer path.
