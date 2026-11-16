# Install OpenClaw Enterprise

Open a terminal in the extracted bundle directory. Read `RELEASE_NOTES.md` if
present. Install Python 3.12+, Node 24+, Bash, Helm 3, kubectl, psql, jq, Mike Farah
yq v4, and OpenSSL. Use OCE's [production prerequisites](https://github.com/raw-labs/openclaw-enterprise/blob/main/docs/guides/deploy.md#production-prerequisites)
to prepare your cluster, database, storage, and network.

## Render site inputs

Set these shell variables for your site.

| Variable | Value |
| --- | --- |
| `SITE` | Absolute path to a private directory outside the bundle |
| `KUBECONFIG_FILE` | Absolute path to the kubeconfig for your cluster |
| `CONTEXT` | Kubernetes context to use |
| `PROFILE` | `openclaw` or `codex` |
| `ARCHITECTURE` | Runtime node architecture, `linux/amd64` or `linux/arm64` |

```bash
umask 077
mkdir -p -m 700 "$SITE"
bin/prepare verify
```

For a new site, copy the example to `"$SITE/site.json"`.

```bash
cp examples/installations/site.json "$SITE/site.json"
```

Edit `site.json` to match your site. Replace the example domains, network ranges,
node labels, and storage class. See [OCE's profile inputs](https://github.com/raw-labs/openclaw-enterprise/blob/main/docs/guides/deploy/installation-profiles.md)
for the fields. If K3s evaluates network policy after translating the Kubernetes
Service address, put the backend CIDR in `controlPlane.clusterCidrs` and set
`cluster.port` to the backend port (usually `6443`) in the Helm overrides.

```bash
bin/prepare render --input "$SITE/site.json" --profile "$PROFILE" \
  --architecture "$ARCHITECTURE" --output "$SITE/rendered"
```

If your site needs an override, add the relevant option to the render command.

| Option | Use |
| --- | --- |
| `--mirrors FILE` | Supply digest-preserving mirror references for `controller`, `runtime`, and `repositoryCredentials`. |
| `--helm-overrides FILE` | Set `cluster.port` or channel listener settings. |
| `--installation-overrides FILE` | Set the namespace Pod quota, native session capacity, repository credential session duration, or channel callback hostname. Set the same hostname in both override files. |

Review `values.yaml`, `installation.yaml`, and `rendered.yaml` in the output
directory. If settings change, edit the inputs and render to a new directory.
To recheck the pair, run `bin/prepare check --directory "$SITE/rendered"`.

## Check the target

Set `PG_SERVICE` to the database's libpq service name and
`BOOTSTRAP_STORAGE_CLASS` to the storage class for the bootstrap PVC. Set
`API_POLICY_DESTINATION` to `service`, `endpoint`, or `both` based on which
destination the cluster's network policy evaluates. For the K3s setup above,
use `endpoint`.

```bash
bin/prepare preflight --directory "$SITE/rendered" \
  --kubeconfig "$KUBECONFIG_FILE" --context "$CONTEXT" \
  --pg-service "$PG_SERVICE" --api-policy-destination "$API_POLICY_DESTINATION" \
  --bootstrap-storage-class "$BOOTSTRAP_STORAGE_CLASS"
```

This read-only check covers PostgreSQL, Kubernetes API policy, node pools,
storage classes, and the packaged seccomp policy. Fix reported failures before
installing. To test connectivity from a running workload, use
[OCE's network probes](https://github.com/raw-labs/openclaw-enterprise/blob/main/docs/guides/operate/network-isolation.md).

## Install and verify

```bash
export PATH="$PWD/bin:$PATH"
export OCC_INPUT_DIRECTORY="$SITE/rendered"
export KUBECONFIG_FILE CONTEXT
cd oce
```

Start at [Shared bootstrap PVC and configuration checks](https://github.com/raw-labs/openclaw-enterprise/blob/main/docs/guides/deploy/production-installation.md#shared-bootstrap-pvc-and-configuration-checks)
in OCE's installation guide. Use the rendered files and bundled chart. Set the
bootstrap PVC's name, namespace, and storage class to match your site.

Confirm that `occ installation get` succeeds with your credentials, then open
[OPERATE.md](operate.md). Before deploying Codex Agents, install the policy from
`security/seccomp/` at the node path set in the Installation.
