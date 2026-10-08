# Select, build and release

For bundle maintainers selecting sources, running CI and publishing releases.
Run commands from this repository with authorized GitHub access.

Release JSON owns source pins, image digests, inventories and evidence. Build inputs
are in the [checkpoint](../releases/source-checkpoint.json); runtime/tool setup and
test commands are in the [workflows](../.github/workflows/). See
[versions and distribution](distribution.md) for version and delivery policy.

## Prepare

Set `RELEASE_ID` to a new prerelease identity and export its exact sources:

```bash
python3 scripts/stock.py new --id "$RELEASE_ID" --output .work/candidate.json
python3 scripts/stock.py --selection .work/candidate.json source --output .work/source
python3 scripts/stock.py --selection .work/candidate.json dependencies --output .work/renderer-dependencies
```

For new source pins, update and verify the
checkpoint and its inventory, then commit them before dispatch: CI reads the
repository checkpoint. `stock.py new --checkpoint <file>` supports local preparation.
Source exports use Git objects, not working-tree content; `source --from-git <path>`
can use a read-only local repository.

## Build and publish images

Dispatch the native build on main:

```bash
gh workflow run build.yml --ref main -f release_id="$RELEASE_ID" -f publish=false
```

The Depot jobs build and test both architectures. Inspect the completed jobs and
native receipts before publication. New artifacts remain unqualified until review.
The workflow's `publish=true` input also supports build and publication in one run
when the private destination is already authorized. To publish an existing successful
build without rebuilding, set `BUILD_RUN_ID` and dispatch:

```bash
gh workflow run publish.yml --ref main -f release_id="$RELEASE_ID" -f build_run_id="$BUILD_RUN_ID"
```

Download the private candidate records and bundle, preserving their file layout.
Inspect any partial publication before retrying. An existing tag is reusable only
when its index matches exactly; never overwrite it. These workflows do not create
a Git tag or GitHub Release.

## Review and deliver

Review the final image digests, native receipts and confinement profiles. Record
acceptance in a JSON review record bound to those exact artifacts; the CLI validates
its required fields. Provider access and customer installation checks remain separate.
Set `REVIEW_RECORD` to that record's path and `RELEASE_SELECTION` to a new output path.

```bash
python3 scripts/stock.py --selection .work/published/candidate.json accept \
  --review "$REVIEW_RECORD" --output "$RELEASE_SELECTION"
python3 scripts/bundle.py --release "$RELEASE_SELECTION" package \
  --source .work/source --dependencies .work/renderer-dependencies --output dist/bundle.tar.gz
```

Verify the delivered inventory, reproducibility and real chart rendering. Build
inputs, image exports, credentials and raw test logs stay outside the SE archive.
Commit the new selection, referenced evidence and artifact record without changing
historical records. Before pushing or creating a private prerelease, verify identity,
origin, repository privacy and expected remote head. Tag the reviewed commit and
attach the archive, checksum and referenced records. Preserve published history;
stable promotion is a separate release-owner decision.
