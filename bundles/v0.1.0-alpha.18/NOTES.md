# Compatibility and upgrade notes

## Existing installations

The Installation plugin-driver setting is now a list rather than a single driver.
Outbound model policy uses the shared Installation proxy instead of per-Agent
gateway outbound settings. Review the packaged OCE upgrade procedure and compare
newly prepared inputs with the retained live baseline; do not replace live settings
with the example profile. Accounts and provider credentials remain installation-owner inputs.

## Agent plugin catalog migration: unresolved upgrade concern

A real PostgreSQL upgrade probe creates and successfully provisions an Agent
through the alpha.17 API with a catalog plugin selection, then runs the candidate's
full migration sequence. It fails at `0071_agent_plugin_driver.sql`: the new
constraint requires a driver but the migration does not backfill one. A matching
API-created Agent without catalog selections upgrades successfully. Compute and
configuration drivers in this probe are test fixtures; it is not a full production
installation upgrade. Check the actual baseline before scheduling one.
See [upstream PR 4174](https://github.com/openclaw/openclaw-enterprise/pull/4174).

These selections are OCE-managed plugin catalog selections. Merely having the
native Connections package installed, or enabling it in OpenClaw configuration,
does not establish that this database field is nonempty. Do not delete selections
or guess their catalog owner to bypass migration. Preserve the database baseline
and use an upstream-supported remediation if the installation is affected.

## Native Connections package

The selected package removes its earlier OpenClaw compatibility upper bound.
Declared compatibility is not runtime or installation qualification. Consult the
release's native receipts and installation evidence separately; external provider
access and customer acceptance remain installation-owner checks.
