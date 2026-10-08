# Install a delivered bundle

For sales engineers and installation operators performing a fresh installation.
Run commands from the extracted bundle root. Keep cluster configuration and
credentials in the operator's private installation directory.

## Obtain artifacts and prepare the cluster

Obtain the archive and checksum through an authorized private release, then verify,
extract and run `python3 scripts/install.py verify`. Read `release.json` for the
selected images, architectures and acceptance scope. Image access is separate:
authorize node pulls or arrange a digest-preserving customer mirror. Installation
uses the delivered chart and images; it does not require building from source.

Use Bash, Python 3.12+, Node 24+, Helm 3 and kubectl compatible with the cluster.
Prepare a dedicated kubeconfig/context, PostgreSQL with separate restricted
application/migration roles and TLS CA, DNS/TLS, RWO storage, disjoint control/Agent
node pools, enforced NetworkPolicies, cert-manager, Gateway API and Envoy.
Cloud prerequisites and node confinement are the installation operator's responsibility.

## Render installation inputs

Copy `examples/installations/aws.json` into the private installation directory as
`site.json`. Replace its example addresses, domains, email, selectors and storage
settings. Review the cluster requirements against the chosen source revision in
`release.json`; the example does not establish support for another environment.

Set `SITE`, `KUBE`, `CONTEXT` and `SECURE` to the installation directory, kubeconfig,
reviewed context and protected credential directory. Set `PROFILE` to `codex` or
`openclaw` and `ARCHITECTURE` to the native target listed in `release.json`.

```bash
umask 077
python3 scripts/install.py render --input "$SITE/site.json" --profile "$PROFILE" \
  --architecture "$ARCHITECTURE" --output "$SITE/rendered"
```

For mirrors, add `--mirrors "$SITE/mirrors.json"`: map each role in `release.json`
to an authorized destination with the same digest. Unqualified candidates cannot
be installed.

Review `preflight.json`, `selection.json`, `values.yaml`, `installation.yaml`,
`rendered.yaml` and supplemental resources. Preserve the paired Installation
checksum. Provision the selected Codex seccomp file on each dedicated harness
node at the path rendered in `installation.yaml`; test it on the actual node
configuration. Review API/DNS/webhook access for prerequisite controllers and the
actual ingress peers, including ALB subnet inputs where applicable. Keep the
Envoy admin listener private.

Set `NAMESPACE`, `RELEASE`, `BOOTSTRAP_CLAIM`, `CONTROLLER` and `CONTROL_SELECTOR`
from `selection.json`'s namespace, releaseName, bootstrapClaim, controller image
and controllerNodeSelector. Use each selector as a separate `--node-selector`
argument when more than one is present.

## Provision protected inputs

Retain the database URLs, public database CA, auth key and gateway key under
`SECURE`, with directory mode 0700 and file mode 0600. Database URLs must verify
TLS and use the CA path rendered for the controller. Generate cryptographically
random auth/gateway keys once and preserve them on upgrades.

Read Secret names and keys from the delivered chart defaults
(`helm show values chart/*.tgz`) together with generated `values.yaml`. Create
these inputs in `NAMESPACE` before Helm runs:

| Input | Configuration that selects its Secret and keys |
| --- | --- |
| Generated `installation.yaml` | `installation.secretName`, `installation.key` |
| Application and migration database URLs | `database.secretName`, `database.appUrlKey`, `database.migrationUrlKey` |
| Public database CA | `database.caSecretName`, `database.caKey` |
| Auth key | `auth.secretName`, `auth.secretKey` |
| Gateway key | `gatewayRouting.apiKeySecretName`; the upstream routing procedure uses key `occ` |

Create the namespace, then create each Secret from the protected files with
`kubectl create secret generic --from-file`. For example, set `SECRET_NAME`,
`SECRET_KEY` and `INPUT_FILE` from the reviewed configuration and table:

```bash
kubectl --kubeconfig "$KUBE" --context "$CONTEXT" create namespace "$NAMESPACE"
kubectl --kubeconfig "$KUBE" --context "$CONTEXT" -n "$NAMESPACE" create secret \
  generic "$SECRET_NAME" --from-file="$SECRET_KEY=$INPUT_FILE"
```

Use both database URL files in the same database Secret. Never put Secret values
in command arguments, rendered configuration or Git. Inspect existing inputs on
a failed creation; preserve identities and credentials rather than replacing them.

## Install and bootstrap

```bash
kubectl --kubeconfig "$KUBE" --context "$CONTEXT" apply --dry-run=server \
  -f "$SITE/rendered/rendered.yaml" -f "$SITE/rendered/supplemental.json"
kubectl --kubeconfig "$KUBE" --context "$CONTEXT" apply \
  -f "$SITE/rendered/supplemental.json" -f "$SITE/rendered/bootstrap-pvc.json"
bash upstream/scripts/prepare-bootstrap-volume --kubeconfig "$KUBE" --context "$CONTEXT" \
  --namespace "$NAMESPACE" --claim "$BOOTSTRAP_CLAIM" \
  --image "$CONTROLLER" --node-selector "$CONTROL_SELECTOR"
helm upgrade --install "$RELEASE" chart/*.tgz --kubeconfig "$KUBE" --kube-context "$CONTEXT" \
  --namespace "$NAMESPACE" -f "$SITE/rendered/values.yaml" --wait --timeout 15m
python3 scripts/install.py bootstrap-read --directory "$SITE/rendered" \
  --kubeconfig "$KUBE" --context "$CONTEXT" --output "$SECURE/bootstrap"
```

The volume helper requires a fresh root and retains a failed Pod for diagnosis.
Helm owns migration/bootstrap ordering. Sign in using the privately retained
bootstrap password, read the OCE Namespace ID and set `TENANT_ID` to that value.

```bash
python3 scripts/install.py tenant-resources --tenant-id "$TENANT_ID" \
  --namespace "$NAMESPACE" --release-name "$RELEASE" --kubeconfig "$KUBE" \
  --context "$CONTEXT" --output "$SITE/tenant-rbac.json"
```

Review the generated grants, then apply:

```bash
kubectl --kubeconfig "$KUBE" --context "$CONTEXT" apply -f "$SITE/tenant-rbac.json"
```

Repeat into a new output after the gateway
namespace appears and require OCE Namespace readiness. Import optional
`defaults/*-preset.json` through the authenticated Namespace preset API
(`POST /namespaces/<id>/presets`, JSON file as body), or use seeded templates.
Create model Secrets, grant Agent access and deploy through the Console. Review
template settings and add the deployed Agent's HTTPS origin before native UI use.
Optional public TCP egress requires `--public-egress --agent-id <id>` and review
of the generated policy for that Agent.

For optional Git repository access, configure the customer GitHub App, broker
registry and TLS using `upstream/docs/guides/repository-credentials/installation.md`.
Use the release's shipping image digests and delivered chart in place of that
upstream guide's build steps. Review its exact-source links and arrange access
before enabling this capability; referenced tools are not all included in the bundle.

Record acceptance using the checks in the delivered `OPERATE.md` before handoff.
