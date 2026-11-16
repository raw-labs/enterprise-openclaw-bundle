# Update OpenClaw Enterprise

Keep the currently installed bundle and extract the new one beside it. Start
in the new bundle directory and read `RELEASE_NOTES.md` if present. You need
the tools listed in [INSTALL.md](install.md). OCE's image probe also requires
native Linux on AMD64 or ARM64, UID 1000, and Docker CLI and Engine 28.1 or
later with the containerd image store enabled.

## Back up the installation

Follow OCE's [upgrade checklist](https://github.com/raw-labs/openclaw-enterprise/blob/main/docs/guides/deploy/upgrade-checklist.md)
and [backup procedure](https://github.com/raw-labs/openclaw-enterprise/blob/main/docs/guides/deploy/upgrade-baseline.md).
Save the live Helm values and Installation. The upgrade helper needs both.

## Check the target

Set `SITE`, `KUBECONFIG_FILE`, `CONTEXT`, and `ARCHITECTURE` as shown in
[INSTALL.md](install.md#render-site-inputs). Set `PG_SERVICE` and
`API_POLICY_DESTINATION` as shown in the [target checks](install.md#check-the-target).
Set `RELEASE` and `NAMESPACE` to the live Helm release and namespace. Set
`LIVE_INSTALLATION` to the absolute path of the saved Installation file.

```bash
umask 077
mkdir -p -m 700 "$SITE"
bin/prepare verify
helm get values "$RELEASE" --all --output yaml --namespace "$NAMESPACE" \
  --kubeconfig "$KUBECONFIG_FILE" --kube-context "$CONTEXT" > "$SITE/live-computed-values.yaml"
bin/prepare preflight --live-values "$SITE/live-computed-values.yaml" \
  --live-installation "$LIVE_INSTALLATION" --architecture "$ARCHITECTURE" \
  --kubeconfig "$KUBECONFIG_FILE" --context "$CONTEXT" \
  --pg-service "$PG_SERVICE" --api-policy-destination "$API_POLICY_DESTINATION"
```

Use `live-computed-values.yaml` for preflight. Use the original saved Helm
values for the upgrade itself.

## Resolve compatibility issues

- If the new version requires `drivers.plugin` as an array, wrap the existing
  entry in a copy of the Installation. Pass that copy as `--candidate-installation`
  and the original as `--installation`.
- If the live Installation uses `runtime.gatewayOutbound` and the new version
  uses the shared proxy, plan a replacement policy with the installation owner
  before removing the old setting. The image upgrade rejects the old setting.
- If a path in `presets.files` will be absent from the new image, remove it
  using OCE's [Installation change procedure](https://github.com/raw-labs/openclaw-enterprise/blob/main/docs/guides/deploy/production-installation-changes.md)
  while the old controller is running. Capture the baseline again. Stored presets
  stay in place.

## Run the upgrade

Schedule downtime and keep your backup. Helm rollback leaves database migrations
in place.

Follow OCE's [production upgrade procedure](https://github.com/raw-labs/openclaw-enterprise/blob/main/docs/guides/deploy/production-upgrade.md).
Run the helper from `oce/` and set `--occ ../bin/occ` to use the bundled CLI.
Use `sources.oce.commit` for the source revision and `images.*.reference` for
the image digests in `metadata/release.json`.

After the upgrade, follow [OPERATE.md](operate.md). If it stops partway through,
keep the baseline, backup, and evidence and follow
[OCE's recovery guide](https://github.com/raw-labs/openclaw-enterprise/blob/main/docs/guides/deploy/production-upgrade-recovery.md)
before retrying.
