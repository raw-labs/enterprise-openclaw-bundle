# Operate an installation

For installation owners. OCE owns operational behavior; the bundle supplies
matching artifacts and exact-source tools. Run OCE procedures from `upstream/`.

## Accept and retain

Keep the downloaded archive/checksum, site inputs, generated configuration,
image/mirror selection and Helm release identity. Protect credentials and
database/PV backups according to the installation's recovery policy.

Before handoff, verify image pulls, authenticated `occ installation get`, Console
sign-in, Namespace readiness, a real Agent/model turn, workspace persistence,
access restrictions and confinement on the actual nodes. Test enabled plugins,
repository access and external identity providers separately. Bundle artifact
checks do not establish acceptance of a customer's environment.

## Diagnose

From the bundle root, run `python3 tools/prepare.py verify` and
`python3 tools/prepare.py check --directory "$SITE/rendered"`.
These check local files and chart rendering. Use OCE's procedures and ordinary
kubectl/Helm commands for cluster health; retain diagnostic logs privately.

## Upgrade and recover

Use the candidate bundle's packaged
[production image upgrade procedure](upstream/docs/guides/deploy/production-upgrade.md)
and [recovery procedure](upstream/docs/guides/deploy/production-upgrade-recovery.md).
The helper and its sibling probes, chart and Collector configuration are included.
Read its supported changes and prerequisites before running it.

The verified candidate's `upstream/` replaces the source checkout in that guide;
skip its Git checkout and CLI build steps. Put the candidate bundle's `bin/` on
PATH to use the matching `occ`. Substitute your actual namespace, Helm release
and protected directories for upstream examples. Optional source-level Name
diagnostics in the recovery guide require an OCE checkout; the packaged upgrade
helper already validates the Installation name during preflight.

Use the new bundle's selected image digests and OCE source revision from
`release.json`. Retain protected baseline values and Installation files;
render candidate inputs into a separate directory when settings must change.
Follow upstream's backup, Installation binding, maintenance, migration and
recovery steps. Fresh-install volume preparation is not an upgrade step.
Helm rollback does not reverse database migrations.
