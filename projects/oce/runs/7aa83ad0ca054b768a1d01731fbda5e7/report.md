# Maintenance run 7aa83ad0ca054b768a1d01731fbda5e7

Status: **running**

Recipe: `a14318257f37ed6f62957d35df94021cf4cfa8f7`
Upstream: `8e20e2019fb4d067e0876fb10e59231dd70c5761`

Candidate: `not qualified`
Tool: `0.1.0`, source digest `a0fc33333b96b0bd104a785ebab7bb62aba0dd93cee32c39e1c14f1ac1162704`
Worker: `codex`, requested model `gpt-6-astra`, effort `high`

## Features

| Feature | Source | Refreshed | Assessment / decision |
| --- | --- | --- | --- |
| profiles | `5acf92b89f9053fec747a802e3790822a5b4340d` | `pending` |  pending |
| secrets | `b698b30abc802185905bf4ff28792a7b9cc1c04e` | `pending` |  pending |
| plugins | `65dc3e90ecb0799ddeb22899bbbc41a5548d37a1` | `pending` |  pending |
| roles | `f30db5c4045cbf2c1f5eef4576361112535ed8b4` | `pending` |  pending |
| first-admin | `37fac70dfb784351544189ad07909588b327ef47` | `pending` |  First-admin remains useful and is not absorbed by frozen upstream. Retain its deployment-time preparation, preserve upstream improvements, and adapt it to the selected per-person roles feature. No intent decision or mandatory source dependency was identified. No files or remote state were changed. |
| outbound | `a50b14647d4311764cce3359150149bc81f23431` | `pending` |  pending |
| teams | `93c1dc4f24b9f544b26a451b71a0cfeff34be4fc` | `pending` |  pending |
| embedded | `94346f8101230627f206ed9731f2c32beba27bad` | `pending` |  The embedded Slack/Teams trial remains useful and is not absorbed by frozen upstream. Integration requires a Configuration-save regression repair and the authorized outbound, provider, and callback adaptations. No intent decision is needed. Assessment only; no files, Git state, or remote resources changed. |

## Composition

Order: embedded → first-admin → outbound → plugins → profiles → roles → secrets → teams


## Verification


### embedded-assess

The embedded Slack/Teams trial remains useful and is not absorbed by frozen upstream. Integration requires a Configuration-save regression repair and the authorized outbound, provider, and callback adaptations. No intent decision is needed. Assessment only; no files, Git state, or remote resources changed.
- Remaining feature: at 94346f810, apps/controller/src/drivers/compute/kubernetes/configuration-rules.ts::requireChannelTopology and index.ts add trusted experimentalEmbeddedChannels admission, embedded provisioning, and revision-time checks. At upstream 8e20e2019, requireChannelTopology still rejects embedded channels and agentProvisioning advertises only dedicated execution. Upstream therefore does not supply equivalent behavior.
- Generic refresh regression: 94346f810 index.ts::validateConfigurationContent unconditionally calls requireTeamsConfiguration, including when the trial is disabled. That function requires explicit appId/tenantId UUIDs and an object-shaped appPassword environment reference. Upstream tests/integration/configuration-controller.test.mjs:2197–2334 explicitly accepts saving bound Teams password strings without those deployment prerequisites, including ${MSTEAMS_APP_PASSWORD} and $MSTEAMS_APP_PASSWORD, and accepts corresponding Preset defaults. Applying the trial validator unchanged contradicts that supported workflow.
- Upstream replacement to preserve: c40b22b6f introduced packages/occ/src/channel-secret-bindings.ts and shared Configuration-save/deployment validation; 56af0a512 expanded runtime reference-form coverage. Frozen upstream checks embedded references, fallback expressions, shorthand secret inputs, and unreadable Slack token objects. The feature head's private collectChannelSecretBindingIds recognizes fewer forms and must not replace this shared implementation.
- Outbound composition mismatch: selected outbound a50b14647 replaces runtime.channels.proxyUrl transport with immutable revision.gatewayOutbound snapshots. index.ts::admitGatewayOutbound currently refuses nonempty requirements for embedded execution. The embedded feature instead uses runtime.channels.proxyUrl/managedProxy and the shared slack-proxy.mjs. Thus the requested managed channel-derived path needs an adapter; neither source independently implements the combined behavior.
- Provider compatibility concern: embedded index.ts applies HTTPS_PROXY and NODE_USE_ENV_PROXY to the combined Gateway/model process, with NO_PROXY limited to local/service destinations. Its slack-proxy.mjs allows Slack and optionally five Microsoft hosts, excluding model endpoints. Outbound a50b14647 similarly supplies only internal bypass hosts in gatewayOutboundTransport. Preserving native model execution therefore requires the authorized provider adaptation; channel-only proxy acceptance does not prove model connectivity.
- Teams composition overlap: embedded index.ts::reconcileTeamsCallback and Teams head 93c1dc4f2 both manage the same Agent callback resource names and public listener. Embedded adds a revision-selecting callback Service and NetworkPolicy; Teams derives callback ownership from the serving Deployment and supplies directory/editor/media support. These are overlapping implementations to reconcile, not evidence that either feature requires restacking on the other.
- Consequential upstream changes must survive: 774b3d676 introduced discoverable Driver configuration validation; 908ffe5be enforces Gateway tool policy at save and for embedded Agents; 854b1ddf5 centralizes runtime source metadata. Frozen upstream deploy/runtime/openclaw-source.json pins 554f0b886bde6c089578c49967227f8b50d1cf16. Port the opt-in and Teams packaging onto these current owners rather than restoring the older constructor, validation, or runtime-image implementation.
- Verification performed: node scripts/ci/run-tests.mjs audit passed at 94346f8101230627f206ed9731f2c32beba27bad, with 391 discovered files, 391 selected files, and no issues. No installed node_modules graph exists in this checkout. Runtime, browser, Kubernetes, PostgreSQL, and hosted CI results were not established in this assessment; no dependencies were installed.
- Existing behavioral proof: tests/conformance/kubernetes-compute.test.mjs covers trusted opt-in/default refusal and callback candidate fencing. tests/integration/kubernetes-compute-provisioning-real.test.mjs contains the regular API/PostgreSQL/Kubernetes scenario covering exact Secret projection, revision replacement, Teams disable/reenable, and stop after disabling the option. Its comments explicitly exclude native Teams dispatch, JWT verification, public TLS, and model execution. Historical passes in the implementation plan do not qualify the frozen-upstream combination.
- The embedded feature changes no migration files relative to a7aa9219f. It provides no reason to alter previously published migration SQL or journal entries.

### first-admin-assess

First-admin remains useful and is not absorbed by frozen upstream. Retain its deployment-time preparation, preserve upstream improvements, and adapt it to the selected per-person roles feature. No intent decision or mandatory source dependency was identified. No files or remote state were changed.
- At 37fac70dfb784351544189ad07909588b327ef47, packages/occ/src/index.ts calls optional Compute.configureAgent with the allocated Agent during deployment admission. Kubernetes native-admin.ts prepares the exact origin and device approval while preserving opt-outs and rejecting conflicts. API composition, worker.ts, worker.mjs, Helm and Compose supply matching origin inputs.
- At upstream 8e20e2019fb4d067e0876fb10e59231dd70c5761, agentRuntimeConfiguration in packages/occ/src/index.ts has no Compute preparation hook. Standard presets enable Control UI without the Agent origin or device approval; tests/integration/native-admin-k3d-real.test.mjs still PATCHes Configuration and redeploys through redeployWithNativeAdminAccess. This demonstrates the remaining first-deployment gap.
- Generic refresh concern: upstream packages/occ/src/gateway-security-defaults.ts supplies sandbox, exec and workspace defaults, and commit 08f3658ed injects the Agent display name into the admitted snapshot. First-admin's tests/integration/native-admin-access.test.mjs asserts revision.configuration.agents equals the unmodified preset. That expectation must accommodate upstream behavior while still proving saved Configuration immutability.
- Generic refresh concern: upstream commit 7ed3402dd hardens native-admin socket closure and audit ownership; tests/conformance/native-admin-upgrade-reset.test.mjs covers delayed denial audits, shutdown and resets. Preserve these changes in apps/controller/src/http/native-admin.ts; first-admin's actual feature delta there only removes the unused revision argument.
- Upstream managed mode remains consequential: tests/integration/native-admin-k3d-real.test.mjs explicitly disables gatewayManagedMode before testing native Configuration writes, then re-enables it and verifies rejection. Automatic first-deployment access must retain that restriction and its test coverage.
- Combination adaptation: at roles f30db5c4045cbf2c1f5eef4576361112535ed8b4, Kubernetes runtime-access.ts requires literal coverage of each assigned role's scopes, and index.ts renders managed identities with allowUsers: []. First-admin instead rejects authored allowUsers other than the service identity and enforces exactly [operator.admin] approval scopes. Simply combining these sources rejects supported role policy or leaves limited roles unavailable.
- Supported tests include first OpenClaw/Codex deployment, sibling-origin isolation, opt-outs and conflicts in native-admin-access.test.mjs; durable provisioning/replay in postgres-agent-provisioning.test.mjs; and API/worker input parity in development-packaging.test.mjs and production-kubernetes-packaging.test.mjs. The HTTP tests simulate cluster effects; they do not prove installed runtime behavior.
- Verification at 37fac70df: node scripts/ci/run-tests.mjs audit passed with no issues; git diff --check passed. node --test tests/integration/native-admin-access.test.mjs failed during module loading because typebox is unavailable, before behavioral tests ran. PostgreSQL, Kubernetes and hosted CI outcomes were not verified. First-admin changes no migration files.

Execution tool source digests: `720c6d896abc9b3a4a1b59a5adbf09cfd1c2bf9456be581f3dc3b3ad9f76bcc0`

## Publication

{}

Checks prove their configured behavior. Detailed worker transcripts and raw logs remain local.
