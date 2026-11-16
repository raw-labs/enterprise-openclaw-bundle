# Verify an installation

1. Check that the Pods can pull their images. Run `occ installation get` with
   your credentials and sign in to the Console.
2. Follow OCE's [Agent setup guide](https://github.com/raw-labs/openclaw-enterprise/blob/main/docs/guides/deploy/production-agents.md).
   Send the Agent a message and check that its workspace persists. Check
   [Codex confinement](https://github.com/raw-labs/openclaw-enterprise/blob/main/docs/guides/topics/standard-codex-preset.md#verify-before-use)
   on the target nodes if enabled.
3. Test the integrations you enabled with their actual accounts and permissions.

Keep the verified archive, site settings and backups. Use [UPDATE.md](update.md)
to update the installation.

## Apply preset changes

OCE adds missing presets and keeps existing copies. You can inspect the
selected templates under `oce/deploy/presets/raw/`. To update a preset, use OCE's
[preset procedure](https://github.com/raw-labs/openclaw-enterprise/blob/main/docs/guides/topics/agent-presets.md).
To change an existing Agent, update and redeploy its Configuration.

## Configure integrations

- **Connections:** Follow the [plugin setup guide](https://github.com/raw-labs/openclaw-connections#install-and-configure),
  skipping package installation. Bind the project key through
  [OCE Secrets](https://github.com/raw-labs/openclaw-enterprise/blob/main/docs/reference/configuration/secrets.md),
  permit outbound access, and verify consent in the Agent's Connections page.
- **Slack and Teams:** Follow OCE's [Slack](https://github.com/raw-labs/openclaw-enterprise/blob/main/docs/guides/integrations/slack.md)
  and [Teams](https://github.com/raw-labs/openclaw-enterprise/blob/main/docs/guides/integrations/teams.md)
  guides. The [experimental embedded mode](https://github.com/raw-labs/openclaw-enterprise/blob/main/docs/guides/integrations/embedded-channel-trial.md)
  shares model and channel credentials in the workload.
- **Repository access:** Use OCE's [broker setup](https://github.com/raw-labs/openclaw-enterprise/blob/main/docs/guides/repository-credentials/installation.md)
  with the packaged image selection.
- **Browser:** If enabled, verify Chromium's sandbox on the target.

## Troubleshoot

| Symptom | First check |
| --- | --- |
| Package verification fails | Verify the download or cache, then extract the archive again. |
| Render rejects an image or policy | Check the release, mirror digests and architecture. |
| Pods cannot pull images | Check the runtime nodes' registry access. |
| Codex cannot start | Check the exact seccomp file at the configured node path. |
| Connections tools are unavailable | Check the key binding, permissions, egress and consent. |

For help, see [SUPPORT.md](support.md). Report suspected vulnerabilities using
[SECURITY.md](../SECURITY.md).
