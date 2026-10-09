# Install a bundle

For operators installing OCE into prepared Kubernetes infrastructure.
Commands and relative links below apply to the extracted package.
Download `bundle.tar.gz` and `bundle.tar.gz.sha256` from the selected private
GitHub release. The remaining assets are build provenance and test evidence.
With GitHub CLI authenticated and an empty download directory:

```bash
: "${VERSION:?Set VERSION to the selected bundle tag}"
: "${DOWNLOAD:?Set DOWNLOAD to an absolute empty download directory}"
gh release download "$VERSION" --repo raw-labs/enterprise-openclaw-bundle \
  --pattern 'bundle.tar.gz*' --dir "$DOWNLOAD"
```

In that directory, verify with `sha256sum -c bundle.tar.gz.sha256` (macOS:
`shasum -a 256 -c bundle.tar.gz.sha256`), extract with `tar -xzf bundle.tar.gz`,
and enter the extracted version directory.

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
python3 tools/prepare.py verify
export PATH="$PWD/bin:$PATH"
occ --version
cp examples/installations/site.json "$SITE/site.json"
```

Edit `site.json` using OCE's [installation input format](upstream/docs/guides/deploy/installation-profiles.md).
Select `openclaw` or `codex` and the target `linux/amd64` or `linux/arm64`:

```bash
PROFILE=codex
ARCHITECTURE=linux/amd64
python3 tools/prepare.py render --input "$SITE/site.json" --profile "$PROFILE" \
  --architecture "$ARCHITECTURE" --output "$SITE/rendered"
python3 tools/prepare.py check --directory "$SITE/rendered"
```

For a mirror, add `--mirrors "$SITE/mirrors.json"` to `render`. Map
`controller`, `runtime` and `repositoryCredentials` to destinations retaining
the release's exact digests. The tool rejects conflicting images and confinement.

Review `preflight.json`, `values.yaml`, `installation.yaml` and `rendered.yaml`.
The tool only prepares files. It does not create Kubernetes resources or credentials.
For Codex, provision the packaged architecture-specific seccomp file at the
node path selected in `installation.yaml`. The selected Codex profile uses RAW's
curated catalog; original upstream profiles remain under `upstream/deploy/profiles/`.

## Install and bootstrap

Change to `upstream/` and follow the packaged
[production installation procedure](upstream/docs/guides/deploy/production-installation.md#shared-bootstrap-pvc-and-configuration-checks)
from **Shared bootstrap PVC and configuration checks** onward. Use absolute paths:

```bash
export OCC_INPUT_DIRECTORY="$SITE/rendered"
cd upstream
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
[production Agents](upstream/docs/guides/deploy/production-agents.md) and, when enabled,
[repository access](upstream/docs/guides/repository-credentials/installation.md).
Use the selected release images instead of upstream image-build steps.
Human sign-in and presets use OCE's APIs and Console; optional RAW preset files
are in `defaults/`. Packaged `occ` supports remote administration;
`occ dev` requires an OCE source checkout.

Follow [OPERATE.md](OPERATE.md) for acceptance and upgrades. Each installation
uses its own OCE inputs; the same immutable bundle can serve multiple clusters.
