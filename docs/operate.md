# Operate an installation

For installation owners. OCE owns operational behavior; the bundle supplies
matching artifacts and exact-source tools. Run OCE procedures from `oce/`.

## Accept and retain

Keep the downloaded archive/checksum, site inputs, generated configuration,
image/mirror selection and Helm release identity. Protect credentials and
database/PV backups according to the installation's recovery policy.

Before handoff, verify image pulls, authenticated `occ installation get`, Console
sign-in, Namespace readiness, a real Agent/model turn, workspace persistence,
access restrictions and confinement on the actual nodes. Test enabled plugins,
repository access and external identity providers separately. Bundle artifact
checks do not establish acceptance of a customer's environment.

## Presets and native plugins

OCE seeds selected RAW presets when it starts and when a Namespace is created.
Existing same-name presets are preserved, including operator edits; changed
bundle templates do not automatically replace them.

Selected native plugins are already in the runtime image. Enable them through
OCE's [native Configuration values and Secret bindings](oce/docs/reference/configuration/secrets.md).
Add the plugin ID to `plugins.allow` and configure `plugins.entries`.
For Connections, use `openclaw-connections`, an `env` SecretRef to a bound
`COMPOSIO_API_KEY`, and OpenClaw's custom-plugin UI setting and consent.
The [plugin's instructions](https://github.com/raw-labs/openclaw-connections#install-and-configure)
own provider setup and grants; skip their package-install step.
The complete Connections directory uses the Gateway's private persistent volume.
Verify provider access, grants and retained state in your installation.

## Diagnose

From the bundle root, run `bin/prepare verify` and
`bin/prepare check --directory "$SITE/rendered"`.
These check local files and chart rendering. Use OCE's procedures and ordinary
kubectl/Helm commands for cluster health; retain diagnostic logs privately.

## Upgrade and recover

Start with [UPDATE.md](UPDATE.md). For an interrupted update, retain its evidence
and maintenance restrictions and follow OCE's
[recovery procedure](oce/docs/guides/deploy/production-upgrade-recovery.md).
