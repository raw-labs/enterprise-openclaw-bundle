# Install a delivered bundle

Obtain a versioned `.tar.gz` and `.sha256` through the RAW Labs release owner or
an authorized private release. Receive the checksum through the same trusted
channel. Image access is separate: request read access for every eligible node
or an authorized digest-preserving mirror into the customer's private registry.
No normal installation requires the private build repository or rebuilding images.
Read `release.json` for the selected scope and qualification; baseline evaluation
requires the explicit flag below. Candidates cannot be installed through this tool.

Use Bash, Python 3.12+, Node 24+, Helm 3, kubectl compatible with the cluster,
and a dedicated kubeconfig/context. The installation repository owns a reviewed
cluster, database, DNS/TLS and backup policy. Prepare Kubernetes according to the
selected OCE requirements, enforced NetworkPolicies, Ready disjoint control/agent node pools,
RWO storage, cert-manager, Gateway API CRDs, Envoy and an existing GatewayClass.
On AWS, supply VPC CNI policy enforcement, EBS CSI and ALB ingress separately;
selected dependency requirements are in the bundled upstream documentation. Configure
node pulls for the authorized customer registry, not just workstation login.

Supply a PostgreSQL database with separate restricted application and migration
roles, TLS CA, cluster/database/proxy CIDRs, DNS selectors and operator labels.
Route console and wildcard Agent HTTPS hosts to `openclaw-enterprise-api:8080`
with TLS and WebSocket support. Permit the actual ingress peers through the
control-plane API network policy; `apiClients` labels must match in-cluster ingress.
For ALB, the renderer adds a supplemental API ingress policy from the reviewed
`trustedProxy.cidrs` subnet inputs. Under VPC CNI strict mode, prerequisite
controllers also need installation-owned API/DNS/webhook policies. Keep the Envoy admin listener private.

1. Verify and extract the archive into a work directory, then enter its root:

   ```bash
   shasum -a 256 -c bundle.tar.gz.sha256
   tar -xzf bundle.tar.gz
   cd <release-id>
   python3 scripts/install.py verify
   ```

   Keep customer files in a separate private installation directory. Copy
   `profiles/aws-example.json` there as `site.json`; replace every example address,
   domain, email and selector. Image references are injected from the release.
   If mirroring, supply `mirrors.json` containing exactly `controller`, `runtime`
   and `repositoryCredentials` mapped to verified destination digest references.
   Each digest must match `release.json`; use `--mirrors "$SITE/mirrors.json"` below.

2. Render into a new directory:

   ```bash
   export SITE=/absolute/path/to/customer-installation
   export KUBE=/absolute/path/to/customer-kubeconfig
   export CONTEXT=reviewed-customer-context
   export SECURE=/absolute/path/to/private-inputs
   umask 077
   python3 scripts/install.py render --input "$SITE/site.json" --profile codex \
     --output "$SITE/rendered" --architecture linux/amd64
   ```

   Use `openclaw` for an embedded-only installation. Expect validated chart output,
   paired Installation checksum, `values.yaml`, `installation.yaml`, bootstrap
   PVC, supplemental resources, `selection.json`, `preflight.json` and `rendered.yaml`. Review preflight
   prerequisites and output before applying. Dedicated Codex requires the reviewed
   seccomp artifact installed through node provisioning at
   `/var/lib/kubelet/seccomp/openclaw/codex-<release-seccomp-sha256>.json` on every
   harness node. Select `linux/amd64` or `linux/arm64` from `release.json`; the
   renderer selects its policy and pins the dedicated Agent node selector to that
   architecture. Historical baseline evaluation additionally requires
   `--allow-pilot-baseline`. Verify sandbox execution on each customer's node configuration before acceptance.
   Do not disable confinement to make a test pass.

3. In `$SECURE` retain raw files `application-url`, `migration-url`, `database-ca.pem`,
   `auth-secret` and `gateway-key` with mode 0600. Database URLs use TLS verification
   and `sslrootcert=/etc/openclaw/database-ca/ca.pem`. Generate auth/gateway keys
   once; retain them on upgrade. This refuses existing output:

   ```bash
   mkdir -p "$SECURE"
   chmod 700 "$SECURE"
   python3 - "$SECURE" <<'PYKEY'
   import os, secrets, sys
   from pathlib import Path
   for name in ['auth-secret', 'gateway-key']:
       fd = os.open(Path(sys.argv[1])/name, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
       with os.fdopen(fd, 'w') as f: f.write(secrets.token_hex(32))
   PYKEY
   kubectl --kubeconfig "$KUBE" --context "$CONTEXT" create namespace openclaw-system
   kubectl --kubeconfig "$KUBE" --context "$CONTEXT" -n openclaw-system create secret \
     generic occ-installation-startup --from-file=installation.yaml="$SITE/rendered/installation.yaml"
   kubectl --kubeconfig "$KUBE" --context "$CONTEXT" -n openclaw-system create secret \
     generic occ-database --from-file=application-url="$SECURE/application-url" \
     --from-file=migration-url="$SECURE/migration-url"
   kubectl --kubeconfig "$KUBE" --context "$CONTEXT" -n openclaw-system create secret \
     generic occ-database-ca --from-file=ca.pem="$SECURE/database-ca.pem"
   kubectl --kubeconfig "$KUBE" --context "$CONTEXT" -n openclaw-system create secret \
     generic occ-auth --from-file=secret="$SECURE/auth-secret"
   kubectl --kubeconfig "$KUBE" --context "$CONTEXT" -n openclaw-system create secret \
     generic occ-private-gateway-key --from-file=occ="$SECURE/gateway-key"
   ```

   These commands use the example's release/namespace/Secret names; keep them
   or substitute the corresponding generated settings. Never print or commit
   Secret values. Failed creation requires inspection, not blind replacement.

4. Validate cluster admission, prepare the fresh PVC and install:

   ```bash
   kubectl --kubeconfig "$KUBE" --context "$CONTEXT" apply --dry-run=server \
     -f "$SITE/rendered/rendered.yaml" -f "$SITE/rendered/supplemental.json"
   kubectl --kubeconfig "$KUBE" --context "$CONTEXT" apply \
     -f "$SITE/rendered/supplemental.json"
   kubectl --kubeconfig "$KUBE" --context "$CONTEXT" apply \
     -f "$SITE/rendered/bootstrap-pvc.json"
   CONTROLLER=$(python3 -c 'import json; print(json.load(open(__import__("os").environ["SITE"]+"/rendered/selection.json"))["images"]["controller"])')
   bash upstream/scripts/prepare-bootstrap-volume --kubeconfig "$KUBE" --context "$CONTEXT" \
     --namespace openclaw-system --claim occ-bootstrap-admin-password \
     --image "$CONTROLLER" --node-selector oce-role=control
   helm upgrade --install oce chart/*.tgz --kubeconfig "$KUBE" --kube-context "$CONTEXT" \
     --namespace openclaw-system -f "$SITE/rendered/values.yaml" --wait --timeout 15m
   python3 scripts/install.py bootstrap-read --directory "$SITE/rendered" \
     --kubeconfig "$KUBE" --context "$CONTEXT" --output "$SECURE/bootstrap"
   ```

   The volume helper requires a fresh root; it leaves failed Pods for diagnosis.
   Helm owns migration/bootstrap ordering. Expect Ready API/worker and accepted
   private Gateway routing; readiness alone does not prove model execution.

5. Sign in at the configured console using the privately retained bootstrap
   password. Read the default OCE Namespace ID, then generate and review grants:

   ```bash
   python3 scripts/install.py tenant-resources --tenant-id '<ns_ID>' \
     --namespace openclaw-system --release-name oce --kubeconfig "$KUBE" \
     --context "$CONTEXT" --output "$SITE/tenant-rbac.json"
   kubectl --kubeconfig "$KUBE" --context "$CONTEXT" apply -f "$SITE/tenant-rbac.json"
   ```

   Repeat into a new output after the gateway namespace appears. Require OCE
   Namespace `ready`. Import an optional `defaults/*-preset.json` through the
   authenticated Namespace preset API or use seeded presets. Create model Secrets,
   grant Agent access, and deploy through the Console. Review the preset configuration
   and add the deployed Agent's exact HTTPS origin before using native UI. For reviewed coding public
   TCP access, generate grants with `--public-egress --agent-id '<agt_ID>'` and review
   the policy before applying. Agent IDs and tenant grants belong to the installation.

6. Record actual node image pulls, login, namespace readiness, real embedded/dedicated
   model turns, workspace persistence across a deliberate test redeploy, rejected
   unauthorized access, and Codex sandbox/network checks. If repository access is
   needed, prepare the customer GitHub App and registry using
   `upstream/docs/guides/repository-credentials/installation.md`, rerender with the
   repository fields enabled, then test real Git access and cleanup separately.
   Retain nonsecret acceptance evidence in the installation repository.

For upgrades, obtain a newly qualified release and its migration/recovery guidance,
review the diff of generated values and Installation, preserve credentials and
volume identities, and test restore under the installation's chosen backup policy.
Update the startup Secret and paired checksum before `helm upgrade`; do not assume
Helm rollback reverses database migrations. Revalidate actual Agent revisions.
