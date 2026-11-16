# Install OpenClaw Enterprise

Start in the verified bundle directory. Read `RELEASE_NOTES.md` if present.
Use Python 3.12+, Node 24+, Bash, Helm 3, kubectl, psql, jq, Mike Farah yq v4,
and OpenSSL. Prepare the cluster, database, storage and network using OCE's
[production prerequisites](https://github.com/raw-labs/openclaw-enterprise/blob/main/docs/guides/deploy.md#production-prerequisites).

## Render site inputs

Set `SITE` to a protected absolute directory outside the package and
`KUBECONFIG_FILE` and `CONTEXT` to the intended cluster. Set `PROFILE` to
`openclaw` or `codex` and `ARCHITECTURE` to `linux/amd64` or `linux/arm64`.

```bash
umask 077
mkdir -p -m 700 "$SITE"
bin/prepare verify
export PATH="$PWD/bin:$PATH"
test -e "$SITE/site.json" || cp examples/installations/site.json "$SITE/site.json"
```

Edit `site.json` using OCE's [profile inputs](https://github.com/raw-labs/openclaw-enterprise/blob/main/docs/guides/deploy/installation-profiles.md).
Replace the sample domains, network ranges, node labels and storage class.

```bash
bin/prepare render --input "$SITE/site.json" --profile "$PROFILE" \
  --architecture "$ARCHITECTURE" --output "$SITE/rendered"
```

Review `values.yaml`, `installation.yaml`, and `rendered.yaml`. Change the site
inputs and render to a new directory when settings change. Use
`bin/prepare check --directory "$SITE/rendered"` to recheck the pair.

- **Mirrors:** pass `--mirrors FILE` with `controller`, `runtime` and
  `repositoryCredentials` references that retain the release digests.
- **Overrides:** use `--helm-overrides FILE` for `cluster.port` and channel
  listener settings. Use `--installation-overrides FILE` for namespace pod quota,
  native session capacity, `repository.configuration.sessionDurationSeconds`,
  or the callback hostname. Use the same callback hostname in both files.

## Check the target

Set `PG_SERVICE` to the target database's libpq service and
`BOOTSTRAP_STORAGE_CLASS` to the bootstrap PVC's class. Set
`API_POLICY_DESTINATION` to `service`, `endpoint`, or `both`, according to which
address the CNI evaluates. For K3s with policy applied after translation, use
`endpoint`, the backend CIDR in `controlPlane.clusterCidrs`, and the backend
port (commonly `6443`) in the Helm override.

```bash
bin/prepare preflight --directory "$SITE/rendered" \
  --kubeconfig "$KUBECONFIG_FILE" --context "$CONTEXT" \
  --pg-service "$PG_SERVICE" --api-policy-destination "$API_POLICY_DESTINATION" \
  --bootstrap-storage-class "$BOOTSTRAP_STORAGE_CLASS"
```

Resolve failures before installing. Before deploying Codex Agents, install
the policy from `security/seccomp/` at the node path selected in the Installation.
Use OCE's [network probes](https://github.com/raw-labs/openclaw-enterprise/blob/main/docs/guides/operate/network-isolation.md)
to verify workload connectivity separately.

## Install and verify

```bash
export OCC_INPUT_DIRECTORY="$SITE/rendered"
export KUBECONFIG_FILE CONTEXT
cd oce
```

Follow OCE's [production installation guide](https://github.com/raw-labs/openclaw-enterprise/blob/main/docs/guides/deploy/production-installation.md#shared-bootstrap-pvc-and-configuration-checks)
from **Shared bootstrap PVC and configuration checks**. Use the prepared pair,
packaged chart, and your site context, namespace and release name. Set the
bootstrap PVC's name, namespace and storage class to match the site.

Confirm authenticated `occ installation get` succeeds, then follow
[OPERATE.md](operate.md).
