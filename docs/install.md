# Install a bundle

Use the `INSTALL.md` inside the selected release archive for an installation.
This repository page describes that archive workflow; packaging adapts its links
to shipped files or the selected immutable upstream source.

For operators installing OCE into prepared Kubernetes infrastructure.
Start in the extracted package root. Commands and relative links below apply
to that directory. The preparation tool reads the bundle version and image
digests from `metadata/release.json`.

## Prerequisites

Use Python 3.12+, Node 24+, Bash, Helm 3 and kubectl compatible with the cluster.
OCE's production procedures also use jq, Mike Farah yq v4 and openssl;
its image-upgrade compatibility probe requires Docker on a Linux workstation.
Database baseline and recovery procedures require psql.

Prepare Kubernetes, PostgreSQL roles and CA trust, DNS/TLS, storage, disjoint
control/runtime node pools, enforced NetworkPolicies, cert-manager and Envoy
Gateway as specified by the packaged OCE production guide. Infrastructure,
ingress access and credentials belong to the installation owner.

Authorize private image pulls or arrange a digest-preserving registry mirror.
Images are pulled separately; this archive is not an offline image package.

Before starting, record the reviewed cluster context, release name, namespace,
node selectors, storage classes, ingress endpoints and registry access in the
installation owner's protected workspace. The example CIDRs, labels and domains
are placeholders. A successful render does not prove those resources exist or
that node confinement has been provisioned.

## Prepare OCE inputs

Run from the extracted bundle root. Keep site settings, generated files and
credentials in a protected directory outside the package.

```bash
umask 077
: "${SITE:?Set SITE to an absolute installation directory}"
mkdir -m 700 "$SITE"
: "${KUBECONFIG_FILE:?Set KUBECONFIG_FILE to an absolute protected kubeconfig}"
: "${CONTEXT:?Set CONTEXT to the reviewed Kubernetes context}"
export KUBECONFIG_FILE CONTEXT
chmod 600 "$KUBECONFIG_FILE"
bin/prepare verify
export PATH="$PWD/bin:$PATH"
occ --version
cp examples/installations/site.json "$SITE/site.json"
```

Edit `site.json` using OCE's [installation input format](https://github.com/raw-labs/openclaw-enterprise/blob/main/docs/guides/deploy/installation-profiles.md).
Select `openclaw` or `codex` and the target `linux/amd64` or `linux/arm64`:

```bash
PROFILE=codex
ARCHITECTURE=linux/amd64
bin/prepare render --input "$SITE/site.json" --profile "$PROFILE" \
  --architecture "$ARCHITECTURE" --output "$SITE/rendered"
bin/prepare check --directory "$SITE/rendered"
```

For a mirror, add `--mirrors "$SITE/mirrors.json"` to `render`. Map
`controller`, `runtime` and `repositoryCredentials` to destinations retaining
the release's exact digests. The tool rejects conflicting images and confinement.

Review `preflight.json`, `values.yaml`, `installation.yaml` and `rendered.yaml`.
The tool only prepares files. It does not create Kubernetes resources or credentials.
For Codex, provision the packaged architecture-specific seccomp file at the
node path selected in `installation.yaml`. The selected Codex profile uses RAW's
curated catalog; original OCE profiles are under `oce/deploy/profiles/`.
The delivered seccomp policies are under `security/seccomp/`.

## Install and bootstrap

Change to `oce/` and follow the packaged
[production installation procedure](https://github.com/raw-labs/openclaw-enterprise/blob/main/docs/guides/deploy/production-installation.md#shared-bootstrap-pvc-and-configuration-checks)
from **Shared bootstrap PVC and configuration checks** onward. Use absolute paths:

```bash
export OCC_INPUT_DIRECTORY="$SITE/rendered"
cd oce
```

The prepared files replace that guide's build and profile-rendering steps.
Its chart path, bootstrap PVC example and `scripts/prepare-bootstrap-volume`
are included. Follow its protected Secret creation, volume preparation, Helm
installation and authenticated `occ installation get` check. Keep the paired
Installation checksum; change site inputs and rerender instead of editing the pair.
For documented chart options outside the profile input format, such as
`cluster.port`, update `values.yaml` and rerun `check`. Preserve the selected
images, profile, confinement and paired Installation checksum.

The upstream runbook uses example names `oce`, `openclaw-system` and
`/secure/occ`. Substitute the release/namespace from your site inputs and your
protected credential directory. Create that directory with mode 0700 before
writing credentials. Edit the bootstrap PVC example to use the selected claim,
namespace and an available protected storage class; bootstrap and runtime
storage classes may differ.

OCE owns authentication, tenant permissions and Agent setup. Continue with
[production Agents](https://github.com/raw-labs/openclaw-enterprise/blob/main/docs/guides/deploy/production-agents.md) and, when enabled,
[repository access](https://github.com/raw-labs/openclaw-enterprise/blob/main/docs/guides/repository-credentials/installation.md).
Use the selected release images instead of upstream image-build steps.
The definition selects preset files and whether to seed OCE's additional defaults.
Preparation applies that selection; OCE seeds missing copies automatically.
Presets can enable Connections without a provider key; an installation
owner configures the key and outbound access in OCE as described in
[OPERATE.md](operate.md#connections). Existing same-name presets are preserved.
Selected files are available under `oce/deploy/presets/raw/` for inspection.
The supplied site example enables managed Gateway outbound and disables
`channels.experimentalEmbeddedChannels`. Review its denied infrastructure CIDRs
for your cluster. Slack and Teams are disabled in the Assistant template. To trial
them, an installation owner must explicitly enable the selected channel plugin
and the installation's experimental channel option. This mode shares channel and
model credentials in the Agent workload; restrict it to trusted evaluation.
Configure provider credentials through OCE and follow
its [embedded channel procedure](https://github.com/raw-labs/openclaw-enterprise/blob/main/docs/guides/integrations/embedded-channel-trial.md).
Teams also requires the public callback listener described there.

Both templates disable browser access and experimental plugin UI. Chromium and
the browser plugin remain build ingredients for a separately reviewed operator
opt-in; the templates do not request `noSandbox`. Verify Chromium sandbox support
and OCE confinement on the actual target before enabling it.

Coding requests human approval, workspace confinement and the limited managed
network proxy, with exact source/package hosts in its template. Cached search is
enabled and direct web fetch is disabled. The limited proxy can reject Git HTTPS
POST requests; review any required policy change rather than granting all hosts.
Template settings are editable defaults, not a Pod-wide firewall or proof that the
running Harness enforced them. Follow OCE's
[policy verification procedure](https://github.com/raw-labs/openclaw-enterprise/blob/main/docs/guides/topics/standard-codex-preset.md#verify-before-use).

Human sign-in and Agent setup use OCE's APIs and Console.
Packaged `occ` supports remote administration;
`occ dev` requires an OCE source checkout.

Follow [OPERATE.md](operate.md) for acceptance and [UPDATE.md](update.md) for later updates. Each installation
uses its own OCE inputs; the same immutable bundle can serve multiple clusters.
