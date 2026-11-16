# Build a release

1. Add a [bundle definition](bundle-schema.md) under `bundles/<version>/`. Use
   a new version whenever you change a published bundle.
2. Add `NOTES.md` beside it. Include changes operators need to know and any
   steps they need to take. These notes go into the archive and GitHub release.
3. Run the [contributor checks](../../CONTRIBUTING.md) and inspect the extracted
   archive.

## Run a review build

In GitHub Actions, open **Release bundle** and choose **Run workflow**. Enter
the path to the definition and leave **Publish** off. You can run a review
build from `main` or a reviewed `codex/` branch. Review builds produce archives
for inspection.

The workflow checks both architectures and rehearses a fresh install. To
rehearse an upgrade as well, enter the published starting tag in **Upgrade
from**. The receipts list the baseline and checks run.

From the GitHub CLI, replace `<version>` with the version you're building.

```bash
gh workflow run release.yml --ref main -f definition='bundles/<version>/bundle.json' -f publish=false
```

To include an upgrade rehearsal, also pass `-f upgrade_from='<published tag>'`.

## Publish

Verify the GitHub account, repository origin, visibility, and exact head of
`main`. The GHCR package visibility must match the repository. Run the
workflow on `main` with **Publish** enabled. After the checks pass, the
workflow publishes image indexes and creates the prerelease. Customers
[download the archive and checksum](../distribution.md).

Use **Re-run failed jobs** while the original artifacts are still available and
`main` is at the same commit. Check for partially published assets before
retrying. Published tags, assets, and digests are immutable.
