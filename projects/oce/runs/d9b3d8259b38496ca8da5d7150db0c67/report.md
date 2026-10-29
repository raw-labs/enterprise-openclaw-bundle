# Maintenance run d9b3d8259b38496ca8da5d7150db0c67

Status: **cancelled**

Recipe: `01bfefbf7417c9832b8e8865a9806a6177e8a418`
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
| first-admin | `37fac70dfb784351544189ad07909588b327ef47` | `pending` |  pending |
| outbound | `a50b14647d4311764cce3359150149bc81f23431` | `pending` |  pending |
| teams | `93c1dc4f24b9f544b26a451b71a0cfeff34be4fc` | `pending` |  pending |
| embedded | `94346f8101230627f206ed9731f2c32beba27bad` | `pending` |  Embedded channels are not absorbed by frozen upstream. The trial remains needed, but requires managed-outbound adaptation and a decision about its stricter Teams validation, which conflicts with upstream-supported Configuration saves. No files, Git state, or remote state were changed. |

## Composition

Order: embedded → first-admin → outbound → plugins → profiles → roles → secrets → teams


## Verification


### embedded-assess

Embedded channels are not absorbed by frozen upstream. The trial remains needed, but requires managed-outbound adaptation and a decision about its stricter Teams validation, which conflicts with upstream-supported Configuration saves. No files, Git state, or remote state were changed.
- At upstream 8e20e2019, apps/controller/src/drivers/compute/kubernetes/configuration-rules.ts::requireChannelTopology rejects embedded channels, and index.ts advertises dedicated-only provisioning. Feature 94346f810 adds the trusted experimentalEmbeddedChannels flag, embedded provisioning, and admission/preparation checks; these behaviors remain absent upstream.
- Concrete contract conflict: feature configuration-rules.ts::requireTeamsConfiguration requires literal UUIDs and an env-object appPassword on every Configuration validation, including dedicated configurations. Upstream packages/occ/src/channel-secret-bindings.ts supports additional bound reference forms; tests/integration/configuration-controller.test.mjs:2245–2261 explicitly saves a Teams configuration with '${MSTEAMS_APP_PASSWORD}' and expects HTTP 201. Applying the feature validator unchanged would reject that upstream-supported save.
- The feature does not implement the requested managed outbound path: index.ts projects runtime.channels.proxyUrl, NODE_USE_ENV_PROXY=1 and broad service-domain NO_PROXY entries. scripts/render-installation-profile.mjs accepts the shared managedSlackProxy or runtimeProxyUrl. Outbound a50b14647 instead owns revision snapshots, proxy workloads and withdrawal, but its admitGatewayOutbound explicitly rejects embedded execution with channel requirements.
- Previous integration 90e30b8c provides relevant adaptation evidence in index.ts: the trial flag requires enabled managed Gateway outbound; admitGatewayOutbound permits opted-in embedded channel requirements while additional outbound modes remain dedicated-only; gatewayOutboundTransport exempts selected model endpoints from the channel-only proxy. These adaptations must be reconciled with current upstream, not copied wholesale.
- Standalone feature limitation: apps/controller/src/slack-proxy.mjs denies model destinations while the trial enables process-wide proxy handling. tests/conformance/slack-proxy-tunnel.test.mjs explicitly expects api.openai.com:443 to be denied. The RFC acknowledges that proxy-aware model calls fail through the stock proxy. The Kubernetes fixture uses a closed loopback model endpoint and does not exercise this failure.
- Teams 93c1dc4f and embedded 94346f810 both manage the same '*-msteams' callback resources through different reconciliation implementations. Embedded index.ts::reconcileTeamsCallback supplies an exact-revision Service and avoids publishing candidate callbacks; Teams adds its directory/editor and guarded transport behavior. Keeping both reconcilers would create competing ownership.
- Upstream replacements to retain include shared channel-reference validation introduced by c40b22b6f and strengthened by 56af0a512, Gateway managed mode 110aea388, and embedded tool-policy validation 908ffe5be. Runtime packaging must extend the current deploy/runtime/openclaw-source.json pin, 554f0b886bde6c089578c49967227f8b50d1cf16, rather than restore the feature's older assembly. The ServiceAccount naming helper added by 9016417f6 is behaviorally equivalent to upstream packages/utils/src/hashing.ts::sha256Hex.
- Supported workflow coverage exists in tests/integration/kubernetes-compute-provisioning-real.test.mjs:970: default refusal, trusted enablement, exact Secret projection, cross-Namespace denial, revision replacement, callback disable/reenable, and stop/delete after disabling the option. It explicitly excludes native Teams JWT enforcement, public TLS, provider delivery and model execution.
- Verification performed: node scripts/ci/run-tests.mjs audit passed at 94346f810 with no issues; node --check passed for slack-proxy.mjs and render-installation-profile.mjs; git diff --check passed. No installed node_modules were present, so dependency-backed suites were not run. GitHub reported successful source-head lifecycle and image jobs in run 39616737356, including jobs 119279779995 and 119279779790; log retrieval failed, so leaf test counts and runtime qualification remain unverified.
- The embedded feature changes no migration files. Its CI runner/AppArmor changes are separate infrastructure work, not embedded-channel semantics; they must not override frozen check policy. No obsolete PR16/PR19 implementation is needed.

## Publication

{}

## Current issue

Run cancelled

Checks prove their configured behavior. Detailed worker transcripts and raw logs remain local.
