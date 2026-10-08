# Scope and ownership

The bundle selects exact OCE sources, builds and checks shipping images, packages
the upstream chart and installation tools, and delivers them privately. Sources,
image digests, included payloads and qualification belong in `release.json`.

The installation operator owns the cluster, database, ingress, node confinement,
registry access, Secrets, users, Agents, repository grants, backups and restore
tests. Artifact qualification does not establish acceptance of that installation.
Read the generated `preflight.json` and the selected upstream requirements before
installing; the bundle does not provision infrastructure.

Optional Agent templates are in `defaults/*-preset.json`. Import them through the
authenticated OCE Namespace preset API (`POST /namespaces/<id>/presets`, JSON file
as body), then create and grant the required model Secrets. Templates are not
automatically installed. Catalog configuration is in `defaults/codex-profile.json`.
Plugins, channels and remote endpoints require their own installation configuration.

Persist only supported mounts. OCE-rendered configuration can replace UI edits on
redeploy; preserve installation settings and credentials in the operator's private
repository. Review migration and restore requirements before upgrades.

Delivered charts and images retain upstream licenses. Shipped code is visible to
its recipient; private delivery does not hide code inside an image.
