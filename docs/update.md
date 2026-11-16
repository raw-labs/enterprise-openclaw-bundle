# Update OpenClaw Enterprise

Keep the installed bundle and download the candidate beside it. Start in the
candidate's root and read `RELEASE_NOTES.md` if present. Use the operator tools
in [INSTALL.md](install.md). OCE's image probe additionally needs native Linux
AMD64 or ARM64, UID 1000, and Docker CLI and Engine 28.1+ with the containerd
image store enabled.

## Back up and check the candidate

1. Follow OCE's [upgrade checklist](https://github.com/raw-labs/openclaw-enterprise/blob/main/docs/guides/deploy/upgrade-checklist.md)
   and [baseline and backup procedure](https://github.com/raw-labs/openclaw-enterprise/blob/main/docs/guides/deploy/upgrade-baseline.md).
   Keep the live Helm values and Installation as the upgrade baseline.
2. Set `SITE`, `KUBECONFIG_FILE`, `CONTEXT` and `ARCHITECTURE` as in
   [INSTALL.md](install.md#render-site-inputs), plus `PG_SERVICE` and
   `API_POLICY_DESTINATION` from its [preflight steps](install.md#check-the-target).
   Set `RELEASE` and `NAMESPACE` to the installed Helm release and namespace,
   and `LIVE_INSTALLATION` to the captured Installation file.

```bash
umask 077
bin/prepare verify
export PATH="$PWD/bin:$PATH"
helm get values "$RELEASE" --all --output yaml --namespace "$NAMESPACE" \
  --kubeconfig "$KUBECONFIG_FILE" --kube-context "$CONTEXT" > "$SITE/live-computed-values.yaml"
bin/prepare preflight --live-values "$SITE/live-computed-values.yaml" \
  --live-installation "$LIVE_INSTALLATION" --architecture "$ARCHITECTURE" \
  --kubeconfig "$KUBECONFIG_FILE" --context "$CONTEXT" \
  --pg-service "$PG_SERVICE" --api-policy-destination "$API_POLICY_DESTINATION"
```

Resolve these conditions if they apply:

- If the candidate needs `drivers.plugin` as an array, wrap the existing entry
  unchanged in a copy of the live Installation. Pass the copy as
  `--candidate-installation` and keep the original as `--installation`.
- If the live Installation uses the retired `runtime.gatewayOutbound` and the
  candidate uses the shared proxy, plan the outbound-policy change separately
  with the installation owner. The image upgrade refuses this setting; do not
  remove it without a replacement policy for the workloads that rely on it.
- If a seed file in `presets.files` will be absent in the candidate image, remove
  the path using OCE's [Installation change procedure](https://github.com/raw-labs/openclaw-enterprise/blob/main/docs/guides/deploy/production-installation-changes.md)
  while the old controller is running. Refresh the baseline. Stored presets remain.

## Run the upgrade

Follow OCE's [production upgrade procedure](https://github.com/raw-labs/openclaw-enterprise/blob/main/docs/guides/deploy/production-upgrade.md).
Run the helper from `oce/` with `--occ occ`; skip the source checkout and CLI
build. Use `sources.oce.commit` and `images.*.reference` in
`metadata/release.json`. Pass the original live files to OCE's helper. The
computed values above are for preflight only.

Schedule the interruption and retain the backup. Helm rollback does not undo
database migrations. After the update, follow [OPERATE.md](operate.md). If the
update stops partway through, keep the baseline, backup and evidence and follow
OCE's [recovery guide](https://github.com/raw-labs/openclaw-enterprise/blob/main/docs/guides/deploy/production-upgrade-recovery.md)
before retrying.
