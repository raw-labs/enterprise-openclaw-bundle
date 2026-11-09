# Compatibility and upgrade notes

## Agent creation and credential access

Deploying an Agent grants its principal exact access to referenced Secrets and
credential sources that the deploying caller can operate. This replaces the
fork-only Configuration Secret grant change. Preset access alone does not grant
access to a shared Secret; an installation owner must authorize its intended users.

Where an installation owner configures the upstream default-user Roles and Groups,
new accounts can create and own Agents without Installation administration.
Members save a draft and deploy it separately; Native admin UI provisioning remains
administrator-only. This bundle does not enable those installation IAM settings or
backfill existing account membership.

Existing same-name presets and live Agent settings are preserved. Review the
packaged OCE creation and deployment procedures for the selected installation's
runtime and credential-driver requirements.

## Upgrade checks

Use the packaged upgrade procedure and retain the installation's baseline and
recovery inputs. The selected integration preserves the previous migration prefix;
that source property alone does not prove database, runtime or customer upgrade
compatibility. The retained upgrade baseline is selected in the definition for
native build and extracted-package checks, not evidence that those checks passed.
