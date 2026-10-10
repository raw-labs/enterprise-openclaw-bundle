# Update an installation

For owners of an existing production Kubernetes/Helm installation. The bundle
packages OCE's upgrade tools; OCE defines migration and recovery behavior.
Native artifact checks and fresh-install tests do not prove an upgrade between
two bundle versions. Check the selected OCE's supported starting state before
scheduling the update.

Run OCE's image probe on native Linux AMD64 or ARM64 as UID 1000, with
Python 3, Node.js and OpenSSL available. Docker CLI and Engine must be 28.1 or
newer (API 1.49+) with the
[containerd image store](https://docs.docker.com/engine/storage/containerd/) enabled.
The probe uses platform-specific `docker image inspect` and `docker image save`;
updating only the CLI or enabling only the image store is insufficient. This is
an upgrade-host requirement, not a Kubernetes node Docker requirement.

## Prepare the candidate

Extract the new bundle alongside the retained old bundle. Keep live Helm values,
Installation YAML, site inputs, credentials and backups in their protected site
directory. Start in the new bundle root:

```bash
bin/prepare verify
export PATH="$PWD/bin:$PATH"
read -r RELEASE_SOURCE_SHA CONTROLLER_IMAGE RUNTIME_IMAGE BROKER_IMAGE < <(
  python3 - <<'PY'
import json
with open("metadata/release.json") as f:
    release = json.load(f)
print(release["sources"]["oce"]["commit"], *(
    release["images"][role]["reference"]
    for role in ("controller", "runtime", "repositoryCredentials")
))
PY
)
export RELEASE_SOURCE_SHA CONTROLLER_IMAGE RUNTIME_IMAGE BROKER_IMAGE
```

For registry mirrors, use authorized references retaining those exact digests.
Review differences in sources, patches, plugins and presets between the bundles'
`metadata/release.json`, and complete OCE's
[upgrade checklist](oce/docs/guides/deploy/upgrade-checklist.md) and
[baseline and backup procedure](oce/docs/guides/deploy/upgrade-baseline.md).

## Follow OCE's upgrade procedure

Run from the candidate's `oce/` and follow its
[production image upgrade procedure](oce/docs/guides/deploy/production-upgrade.md).
This directory replaces the release source checkout in that guide; skip its Git
checkout and CLI build steps. Use `--occ occ`, your actual release/namespace and
protected site paths, and the variables above for its source and image arguments.
The matched helper, probes, chart and Collector configuration are packaged.

Retain the live values and Installation as the baseline. An image update preserves
existing Installation settings; rerendered inputs are comparison material, not a
replacement baseline. The helper supports only the candidate setting changes
listed in OCE's guide. Apply other Installation changes separately with its
[documented procedure](oce/docs/guides/deploy/production-installation-changes.md).
Use the bundle matching the currently installed controller for that step.

In particular, newly selected preset files require adding their image paths to
the existing Installation's `presets.files`. First update the controller so it
contains those files, then apply that separate settings change. Paths are recorded
under `presets` in `metadata/release.json`. If the candidate removes a referenced
file, remove that seed reference separately while the old controller still runs;
otherwise the image helper refuses before stopping OCC. Removing a seed reference
preserves stored presets. Existing same-name presets, including
edits, are preserved. Adopt plugin settings and Secret bindings as described in
[OPERATE.md](OPERATE.md#presets-and-native-plugins). Review plugin state compatibility
and verify provider access after the runtime update.

To adopt changed preset templates, first read and retain the installed copies
with `occ preset get ID -o json`. Compare the selected files in
`oce/deploy/presets/raw/`; merge intended settings while retaining site Secret
references and customizations. Update through OCE's Preset HTTP API. Disable
unwanted default seeding in the Installation before using `occ preset delete ID`
to remove reviewed obsolete copies, or startup can recreate them. Deleting a
preset leaves copied Configurations and Agents intact. Template updates affect
future creation only; update/redeploy existing Agent drafts separately.

The helper stops the API and worker while Helm runs database migrations and
bootstrap before rollout. Runtime updates redeploy all running Agents concurrently
from their current drafts. There is no automatic rollback or batching. Plan an
interruption window and backups; Helm rollback does not reverse database changes.

## Verify or recover

Follow OCE's workload checks and the acceptance checks in
[OPERATE.md](OPERATE.md#accept-and-retain). Retain the previous bundle, site baseline,
backups and private upgrade evidence. For a partial failure, follow the packaged
[recovery procedure](oce/docs/guides/deploy/production-upgrade-recovery.md) before
attempting another update. Optional source-level diagnostics in that guide require
an OCE checkout.
