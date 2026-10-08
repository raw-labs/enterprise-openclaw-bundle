# Operate a delivered bundle

For operators responsible for an installed bundle, including installation
acceptance, upgrades and incident diagnosis. Run bundle commands from its extracted
root. Use the installation's protected kubeconfig and reviewed context.
Set `SITE`, `KUBE`, `CONTEXT`, `NAMESPACE` and `RELEASE` from its installation record
before using the commands below.

## Keep an installation record

Retain the archive/checksum, selected `release.json`, node image digests, reviewed
site inputs, mirror map, generated configuration, Helm release/namespace and node
policy files. Record installation acceptance separately from shipping artifact
qualification. Protect database/PV backups and credentials under the operator's
access and recovery policy; keep Secret exports and raw logs out of Git.

## Accept an installation

Verify actual node pulls, console login, OCE Namespace readiness, real model turns
for each execution mode in use, workspace persistence across a controlled test
redeploy, rejected unauthorized access and Codex sandbox/network behavior on each
node configuration. If repository access is enabled, test real Git access and
credential cleanup. Readiness alone is insufficient.

Retain nonsecret outcomes and the identities of the tested artifacts in the
installation record. Plugins, channels and remote services need their own access
and functional checks. Use the settings in `defaults/` as templates; OCE-rendered
configuration can replace UI edits when an Agent is redeployed.

## Diagnose failures

Verify the artifact and rendered configuration first:

```bash
python3 scripts/install.py verify
python3 scripts/install.py check --directory "$SITE/rendered"
kubectl --kubeconfig "$KUBE" --context "$CONTEXT" -n "$NAMESPACE" get pods,jobs,pvc
helm status "$RELEASE" --kubeconfig "$KUBE" --kube-context "$CONTEXT" --namespace "$NAMESPACE"
helm history "$RELEASE" --kubeconfig "$KUBE" --kube-context "$CONTEXT" --namespace "$NAMESPACE"
```

`check` validates files and rerenders the chart; it does not inspect cluster health.
Read Pod events for pull, placement or storage failures. Review initialization Job
status for bootstrap/migration failures; inspect database roles, TLS and connectivity.
For Agent failures, inspect that Agent's revision, granted model Secrets, node
policy and egress. Collect logs privately and redact credentials before sharing.
Keep confinement enabled and retain failed resources until their outcome is understood.

## Upgrade and recover

Obtain the next release's archive, selection and migration/recovery guidance. Keep
the installed artifact and its record. Back up the database and supported persistent
volumes, verify restoration in the operator's recovery environment, and agree the
maintenance window and any Agent redeployments before mutation.

Render the new release into a separate directory from the preserved site inputs.
Review image, chart, configuration and confinement changes; run the delivered
`check` command and server admission checks. Preserve auth/gateway keys, database
roles, bootstrap claim, volume identities and tenant grants. Provision any new
node policy before dedicated Codex workloads use it.

Follow the release's migration-compatible maintenance flow for draining workloads,
stopping controllers and restoring service. Update the startup Secret from the
reviewed new `installation.yaml` and keep its checksum paired with the new Helm
values. Apply reviewed supplemental changes and use the new delivered chart.
Recheck migration outcomes, private routing and the acceptance cases above;
inspect actual Agent revisions and redeploy only the agreed Agents. Fresh-install
bootstrap preparation is not an upgrade step.

After failure, inspect Helm history, initialization Jobs and retained database
state before retrying. Helm rollback does not reverse committed migrations. Use
the release's migration-compatible recovery procedure or a reviewed forward fix;
restore the database and volumes together when recovery requires restoration.
Do not start an older controller against a migrated database without verified compatibility.
Record the resulting release and acceptance after recovery.
