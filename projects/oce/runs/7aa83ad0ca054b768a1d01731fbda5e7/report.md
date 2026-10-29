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
| profiles | `5acf92b89f9053fec747a802e3790822a5b4340d` | `89ba3c69e1c8251278cb40971f6166a00f832de6` |  Profiles remains useful against frozen upstream 8e20e2019: its custom profile input, explicit seeding control, and readable custom starter are not absorbed. Retain the feature with upstream safeguards and fix the profile-file cleanup defect. No intent decision or mandatory source dependency was identified. No files or remote state were changed. |
| secrets | `b698b30abc802185905bf4ff28792a7b9cc1c04e` | `b8510e379cfc9ea301406d4092ba05b09ef1126e` |  Secrets remains useful and is not absorbed by frozen upstream. Retain its saved-Configuration-derived grants while preserving upstream validation and permission handling. No source or configuration was changed. |
| plugins | `65dc3e90ecb0799ddeb22899bbbc41a5548d37a1` | `5521c0280c7907dfd38742986f3d3fef5fa92482` |  The plugins feature remains independently useful and is not absorbed by frozen upstream 8e20e2019. Preserve its allowlist handling and Harness admission checks while retaining newer upstream behavior. No confirmed generic source regression or mandatory dependency on another selected feature was found. Runtime verification remains incomplete. |
| roles | `f30db5c4045cbf2c1f5eef4576361112535ed8b4` | `489576d57120f1f83da371c0dd5a22bc7c7fddf8` |  Roles remains useful and is not absorbed by frozen upstream 8e20e2019. Preserve its exact human/Agent assignments and revocation while retaining upstream transport, runtime, and managed-mode improvements. No intent decision or source restacking is required. No files or remote state were changed. |
| first-admin | `37fac70dfb784351544189ad07909588b327ef47` | `a768ca1bf094392d590034c17c5701d0ab549e8f` |  First-admin remains useful and is not absorbed by frozen upstream. Retain its deployment-time preparation, preserve upstream improvements, and adapt it to the selected per-person roles feature. No intent decision or mandatory source dependency was identified. No files or remote state were changed. |
| outbound | `a50b14647d4311764cce3359150149bc81f23431` | `56854e0730d8fbf6384012426676e16439cb3022` |  Outbound remains useful and is not absorbed by frozen upstream. Retain its revision-owned egress and durable withdrawal behavior, fix the Configuration-save regression, preserve newer upstream validation, and apply the authorized Teams/embedded adaptations. No intent decision is required. No files or remote state were changed. |
| teams | `93c1dc4f24b9f544b26a451b71a0cfeff34be4fc` | `pending` |  Teams is not absorbed by frozen upstream. Retain its editor, directory, callbacks, and guarded media support. One generic deployment-admission defect needs correction; upstream refresh and outbound/embedded composition require separate adaptations. No intent decision is needed. No files or remote state were changed. |
| embedded | `94346f8101230627f206ed9731f2c32beba27bad` | `94c824071c9b0ae248a4ebb4a22d3e44b5532cfc` |  The embedded Slack/Teams trial remains useful and is not absorbed by frozen upstream. Integration requires a Configuration-save regression repair and the authorized outbound, provider, and callback adaptations. No intent decision is needed. Assessment only; no files, Git state, or remote resources changed. |

## Composition

Order: embedded → first-admin → outbound → plugins → profiles → roles → secrets → teams


## Verification

- embedded-checks / source-audit: passed at `94c824071c9b0ae248a4ebb4a22d3e44b5532cfc`; log SHA-256 `9cd1e847bd46345d6e8582006f941d91436fd8669551877c94030fdfea58f802`
- first-admin-checks / source-audit: passed at `a768ca1bf094392d590034c17c5701d0ab549e8f`; log SHA-256 `6e3331ad3042dc5b4e748127ea946164c293961286b07057b80d560a61aaf9f4`
- outbound-checks / source-audit: passed at `56854e0730d8fbf6384012426676e16439cb3022`; log SHA-256 `d2a172cb95716867124cf6f3d1a59323fca2cb92879f60902b55251b77b1b507`
- plugins-checks / source-audit: passed at `5521c0280c7907dfd38742986f3d3fef5fa92482`; log SHA-256 `69d5ba265c4bf118c289f61bfa2de80866e050263f650ab1f6680bf641b59af1`
- profiles-checks / source-audit: passed at `89ba3c69e1c8251278cb40971f6166a00f832de6`; log SHA-256 `7358c112aa6b300f3587dd0f9c56b1b4cfeef975cf047022f9505a6b281b0e78`
- roles-checks / source-audit: passed at `489576d57120f1f83da371c0dd5a22bc7c7fddf8`; log SHA-256 `488f3e70ceca574217d5190cce68549bb26b2b13fc33087fc3ef72cc0f59c74a`
- secrets-checks / source-audit: passed at `b8510e379cfc9ea301406d4092ba05b09ef1126e`; log SHA-256 `760ec357281181432aa8828d54521125683effa2321ba1bb505b4e288376b1d0`
- teams-checks / source-audit: passed at `0a52d37243653170f8924ff1b679bef3239ab695`; log SHA-256 `641e076dd450df60af18aeef649c472a4454218a4e86834a739f814320514917`

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

### outbound-assess

Outbound remains useful and is not absorbed by frozen upstream. Retain its revision-owned egress and durable withdrawal behavior, fix the Configuration-save regression, preserve newer upstream validation, and apply the authorized Teams/embedded adaptations. No intent decision is required. No files or remote state were changed.
- At a50b14647, packages/contracts/src/gateway-outbound.ts defines channelsOnly/restricted/publicHttps selections and immutable requirements. packages/occ/src/index.ts authorizes policy changes with exact-Agent update plus administer and snapshots admission during deployment. Frozen upstream 8e20e2019 has no corresponding GatewayOutbound implementation.
- apps/controller/src/drivers/compute/kubernetes/index.ts:14502 reconciles revision-owned proxies and NetworkPolicies, combines admitted and current exclusion CIDRs, and closes existing proxy Pods before replacing changed policy. apps/controller/src/worker.ts persists REVISION_ACCESS_WITHDRAWAL_PENDING before removal and retries across restored authority. Upstream's existing public-GitHub reader withdrawal is narrower and does not replace this feature.
- Confirmed generic regression: commit 27562ebf56 introduced the blanket proxy-environment rejection in apps/controller/src/drivers/compute/kubernetes/index.ts:4528. Outbound tests/integration/configuration-controller.test.mjs:1260 expects HTTP_PROXY save rejection and replaces the previous acceptance example with APP_REGION. At frozen upstream, the same owning suite explicitly accepts HTTP_PROXY in Configuration saves (around line 1896).
- Upstream replacement to retain: commits c40b22b6f, 56af0a512 and 3918205bc establish shared channel/Secret validation in packages/occ/src/channel-secret-bindings.ts and its Configuration-save callers. Outbound still carries the older recursive collector in Kubernetes Compute. Frozen upstream tests/integration/configuration-controller.test.mjs covers missing bindings, accepted forms, Slack-readable references, and scope to bundled Kubernetes Compute.
- Slack refresh requirements: outbound apps/controller/src/drivers/channel/slack.ts:170 accepts only object references. Upstream commit 6c16c2266 also accepts a whole ${NAME}; tests/conformance/slack-channel-directory.test.mjs explicitly covers it. Preserve upstream 07749e5e7's null terminal cursor handling and the newer proxy-availability diagnostics when adding outbound requirement declarations.
- Teams composition: outbound apps/controller/src/composition/channel.ts selects Slack alone. Selected Teams source 93c1dc4f supplies BundledChannelDriver in apps/controller/src/drivers/channel/index.ts and serving-Deployment-owned callback reconciliation in Kubernetes Compute. Its directory, callback and guarded-media behavior must survive replacement of the old shared outbound proxy.
- Embedded composition: selected source 94346f81 gates channel execution with experimentalEmbeddedChannels. Outbound admitGatewayOutbound and requireChannelTopology currently require dedicated execution; migrations/0064_gateway_outbound.sql also restricts outbound snapshots to dedicated Harnesses. These require the authorized channel-only embedded adaptation, without granting embedded Agents additional restricted/publicHttps authority.
- Migration compatibility: previous integration 90e30b8c published migrations/0056_gateway_outbound.sql and 0057_embedded_channel_outbound.sql. Outbound now carries a changed 0064_gateway_outbound.sql, while upstream publishes 0064_gateway_managed_mode.sql. Copying either branch's migration history wholesale would violate preservation requirements.
- New upstream behavior is distinct: 110aea388 adds Gateway managed mode; 36fb7180e adds Gateway tool policy; 8e20e2019 checks deployability before upgrade stops writers. Preserve these alongside outbound rather than treating them as equivalent egress controls.
- Validation at a50b14647: node scripts/ci/run-tests.mjs audit passed with no issues. The selected dependency-free test 'invalid policy never creates a serving proxy' passed (1 passed, 0 failed). API, PostgreSQL, public transport, Kubernetes and UI proofs were inspected but not executed; node_modules is absent and the environment is read-only.

### plugins-assess

The plugins feature remains independently useful and is not absorbed by frozen upstream 8e20e2019. Preserve its allowlist handling and Harness admission checks while retaining newer upstream behavior. No confirmed generic source regression or mandatory dependency on another selected feature was found. Runtime verification remains incomplete.
- At upstream 8e20e2019, apps/controller/src/console/agents/create.mts:1422–1433 still adds codex to plugins.allow when selecting Codex and removes it when switching away. Feature head 65dc3e90 changes this path to preserve missing, empty and explicit allowlists, deny lists, and explicit Codex disablement.
- At feature head, apps/controller/src/drivers/compute/kubernetes/configuration-rules.ts:31 implements requireHarnessPluginPolicy: it rejects blocked required plugins, malformed allow/deny lists and ambiguous normalized entries. index.ts:4607 and :4619 invoke it through validateAdmittedHarnessAuth for OpenClaw providers and Codex.
- The feature does not move these plugin checks into Configuration save. index.ts:4682 retains validateConfigurationContent and requireConfiguredModelProviders; packages/occ/src/index.ts:5190 retains shared channel Secret-binding validation. Upstream tests/integration/configuration-controller.test.mjs includes unbound-channel refusal and accepted reference-form coverage that must remain intact.
- Upstream commit 908ffe5be adds distinct Gateway tool-policy validation and admission/preparation handling in Kubernetes index.ts. Its tests/conformance/kubernetes-compute.test.mjs covers Configuration save across topologies and maintenance of active embedded revisions. This complements, rather than replaces, native plugin permission checks.
- Upstream commits aa352e92b and 328dacc04 add dedicated Google Workspace installation and operation enforcement. Upstream create.mts also adds savedOpenClawCatalog guidance. These capabilities do not replace Harness-switch preservation.
- tests/browser/console-agent-presets.test.ts:1943 covers allowlist preservation through switches and API persistence, restored drafts, refusal before writes, and explicit repair. tests/integration/console-api.test.mjs:1818 covers Codex/OpenAI/Anthropic admission, updates and deployment refusal. tests/integration/postgres-agent-provisioning.test.mjs:4126 covers stored-plan replay, worker admission and retry before effects; its Driver switch delegates validation to production Kubernetes rules, but does not prove live Kubernetes execution.
- CI ownership audit passed at 65dc3e90 with no issues. Relevant files are registered in checks-browser-2, checks-baseline-1 and postgres-platform. The targeted console-api test could not load because typebox is absent; no behavioral cases ran. The read-only GitHub check-runs request failed because api.github.com was unreachable.
- The feature delta contains no migration changes. Upstream f647b88f4 deletes docs/guides/deploy/breaking-changes.md, which the feature modifies; retain upstream’s deletion. The working tree remains clean.

### profiles-assess

Profiles remains useful against frozen upstream 8e20e2019: its custom profile input, explicit seeding control, and readable custom starter are not absorbed. Retain the feature with upstream safeguards and fix the profile-file cleanup defect. No intent decision or mandatory source dependency was identified. No files or remote state were changed.
- At 5acf92b89, scripts/render-installation-profile.mjs adds --profile-file, validates the supported PluginDriver selection, and forwards presets.includeDefaults. Frozen upstream still reads bundled profiles only and hardcodes includeDefaults: true.
- At 5acf92b89, apps/controller/src/console/agents/presets.mts:551 selects readable default-codex first, otherwise the first readable Preset by sorted name. Upstream's corresponding code at lines 633–634 disables the shortcut without default-codex; manual custom-Preset selection is not equivalent.
- Existing upstream infrastructure already supports startup seeding selection and custom-file overrides in apps/controller/src/composition/installation-presets.ts:115–183. The feature exposes this through the renderer; it does not require a replacement persistence implementation.
- Generic source defect: scripts/render-installation-profile.mjs:2353 removes generated outputs before reading profileFile at line 2356. A trusted profile stored at <out-dir>/preflight.json, directly or through a symlink alias, is deleted before loading. Upstream commit 2d6bc00b6 protects --input using file identity before cleanup, but does not know about the feature's new profileFile input.
- Upstream improvements to retain: 7379613f5 raises renderer Gateway memory requests/limits to 2560Mi/4Gi; b68e3b556, e8beeb3e7 and e94167c14 add Preset Secret operate/create restrictions; 0a17e7549 improves permission guidance. These affect the same renderer and Preset UI owners.
- Supported feature proof includes tests/integration/profile-renderer.test.mjs for explicit profiles, rejected inputs, startup Preset selection and controller checksums; tests/browser/console-agent-presets.test.ts:3623 for readable/absent/denied defaults and custom-starter Agent creation; and tests/integration/postgres-preset-upgrade.test.mjs for persisted operator state across restarts. Cross-revision upgrade proof requires OCC_TEST_PRESET_BEFORE_ROOT and the separate migrator URL; the default test restarts the same revision.
- Composition evidence: outbound a50b14647 replaces renderer channels inputs with gatewayOutbound/controlPlaneOutbound; embedded 94346f810 adds experimentalEmbeddedChannels under the older channels shape. Profiles independently changes PluginDriver selection and Preset seeding. These overlaps require composition adaptation, not source restacking.
- Local verification at 5acf92b89: CI suite registration audit passed with no issues; three Node syntax checks and git diff --check passed. Kubernetes client, pg and Playwright dependencies are unavailable, so behavioral suites were not run locally.
- Hosted CI associated with the frozen feature head is incomplete: run 40105418494 was cancelled, including Checks and Conformance 1 job 120906067347, Console Browser 2 job 120906067439, and PostgreSQL Platform job 120906067478. CI Required failed its cancellation check. This does not establish a product failure or passing feature coverage.

### roles-assess

Roles remains useful and is not absorbed by frozen upstream 8e20e2019. Preserve its exact human/Agent assignments and revocation while retaining upstream transport, runtime, and managed-mode improvements. No intent decision or source restacking is required. No files or remote state were changed.
- At f30db5c40, packages/iam/src/index.ts::authorizeRuntimeAccess requires Agent use permission and exactly one human/Agent runtime assignment. packages/occ/src/index.ts validates assignments against the saved Configuration generation. Frozen upstream has no equivalent runtime-role API; its native-admin entry still requires administer.
- apps/controller/src/drivers/compute/kubernetes/runtime-access.ts resolves configured roles and policy hashes; kubernetes/index.ts separates /people routing from privileged service routing. apps/controller/src/gateway/native-admin-proxy.ts strips caller-supplied authority headers before injecting admitted headers.
- Generic refresh defect: source apps/controller/src/http/native-admin.ts:1125 and :1162 await denial-audit persistence before closing refused upgrades or returning revoked-lease decisions. Upstream commit 7ed3402dd fixes this with separately tracked admission/audit work and immediate transport refusal. Its tests/conformance/native-admin-upgrade-reset.test.mjs and tests/integration/native-admin-session-postgres.test.mjs explicitly cover closure while audit persistence remains pending.
- Upstream compatibility: commits 110aea388 and aa2cfe543 add managed Gateway restrictions and draft-Configuration guidance. Frozen tests/integration/native-admin-k3d-real.test.mjs explicitly disables managed mode for native-edit proof, then verifies writes are refused after managed mode is restored. The roles branch's older native-edit scenario must retain these distinctions.
- Runtime compatibility remains unverified: roles deploy/runtime/Dockerfile pins OpenClaw f8386bc7 and applies openclaw-trusted-proxy-role.patch. Frozen upstream deploy/runtime/openclaw-source.json pins 554f0b886bde6c089578c49967227f8b50d1cf16 and uses newer build/provenance stages. The patch adds native profile-role publication and HTTP/WebSocket enforcement; its applicability and remaining necessity against that exact runtime source were not established locally.
- Combination adaptation: first-admin 37fac70d, apps/controller/src/drivers/compute/kubernetes/native-admin.ts:47, accepts only operator.admin pairing scopes. Roles runtime-access.ts requires every assigned role scope to appear literally in the pairing ceiling. First-admin's preparation also checks the old service-only allowUsers form, whereas configured roles use managed identity boundaries and an empty allowUsers list.
- Migration compatibility: previous integration 90e30b8c contains migrations/0054_agent_runtime_roles.sql. Source migrations/0064_agent_runtime_roles.sql repeats that migration but adds manage_policy to the restriction constraint. Frozen upstream separately has migrations/0064_gateway_managed_mode.sql. Replaying or replacing the published roles migration would violate the required history preservation.
- Supported source coverage includes native-admin-access.test.mjs cases for ordinary sharing, stale Configuration generations, forged headers, assignment changes and deletion; native-admin-session-postgres.test.mjs covers cross-replica role changes and revocation; native-admin-k3d-real.test.mjs contains genuine runtime/browser sharing scenarios. These are distinct proof levels, not interchangeable.
- Verification at f30db5c40: node scripts/ci/run-tests.mjs audit passed with no issues. node --test tests/integration/native-admin-access.test.mjs failed during module loading because @openclaw-enterprise/utils was unavailable; no behavioral assertions ran. No dependencies were installed. PostgreSQL, browser, image and Kubernetes proof was not executed.

### secrets-assess

Secrets remains useful and is not absorbed by frozen upstream. Retain its saved-Configuration-derived grants while preserving upstream validation and permission handling. No source or configuration was changed.
- At upstream 8e20e2019, apps/controller/src/console/agents/create.mts:2219 still iterates stagedChannelSecrets. Existing generic or prebound Configuration Secrets can therefore receive no grant through ordinary Agent creation. Feature b698b30ab:2068 instead deduplicates every accepted binding source and grants exact Agent-principal/Secret operate access.
- packages/contracts/src/secret-bindings.ts has unchanged normalization between the merge base and frozen upstream: exact Secret references, environment delivery, and omitted delivery normalized to env. The feature matches this contract and confirms the saved Configuration and Agent identity before granting access.
- Upstream packages/occ/src/index.ts:13037 already grants all Configuration sources during guided provisioning through provisioningGrantSources and ensureAgentOperateGrants. This covers a separate workflow; it does not replace the remaining ordinary-create fix.
- Upstream c40b22b6f and dac3bfcf0 introduced shared reference validation and provisioning refusal handling. packages/occ/src/channel-secret-bindings.ts and tests/integration/configuration-controller.test.mjs preserve accepted bound references, including Teams interpolation, fallback and shorthand forms.
- Combination concern: embedded head 94346f81 calls requireTeamsConfiguration from validateConfigurationContent, requiring UUIDs and an object-form appPassword. Applied unchanged, this conflicts with upstream's Configuration-save test accepting bound Teams string references. This is an embedded/upstream adaptation, not a Secrets defect.
- Feature tests/browser/console-agent-presets.test.ts covers distinct generic/model Secrets, duplicate-source deduplication, denied grants, retry without duplicate resources, unrelated-Secret denial, and deployment denial after grant removal. tests/integration/kubernetes-compute-real.test.mjs adds real API/PostgreSQL/worker coverage for revocation after admission and before delivery; actual runtime-value verification requires the runtime-image variant.
- Local CI inventory audit passed at b698b30ab: 442 discovered files, 442 selected, no issues. Focused browser execution failed during module loading because @openclaw-enterprise/contracts is unavailable; the workspace check failed because prettier is unavailable. No behavioral pass or hosted-CI result is claimed.

### teams-assess

Teams is not absorbed by frozen upstream. Retain its editor, directory, callbacks, and guarded media support. One generic deployment-admission defect needs correction; upstream refresh and outbound/embedded composition require separate adaptations. No intent decision is needed. No files or remote state were changed.
- Compared Teams 93c1dc4f24b9f544b26a451b71a0cfeff34be4fc with upstream 8e20e2019fb4d067e0876fb10e59231dd70c5761. Upstream recognizes msteams credentials but lacks apps/controller/src/drivers/channel/teams.ts, console/channels/teams.mjs, Teams callback reconciliation, and msteams runtime packaging. Recognition does not implement the requested workflow.
- Remaining functionality: TeamsChannelDriver performs scoped Graph lookup with bounded pagination and checked continuations; BundledChannelDriver selects Slack or Teams. console/channels/teams.mjs supplies editing and Secret binding, while console/agents/teams-directory.mjs supplies directory selection.
- Generic source defect: at Teams HEAD, kubernetes/index.ts:3879 validateHarnessAuth checks channel topology but omits the Teams listener, webhook path, legacy listener, and cloud checks held in enabledChannels at line 13236. Preparation calls enabledChannels at line 6613. worker.ts:1729 stops dedicated predecessors before preparation, so these predictable refusals can cause downtime.
- The owning upstream regression test is tests/conformance/kubernetes-compute.test.mjs, 'deployment admission refuses Gateway breakers before a dedicated deployment stops its predecessors'. Teams currently tests an invalid webhook path through prepareRevision at line 9374, which does not protect early admission.
- Upstream replacements to preserve: c40b22b6f added shared channel-binding validation; 3918205bc rejects unreadable Slack token objects; 6c16c2266 accepts whole ${NAME} token references; 07749e5e7 accepts null terminal Slack cursors. Their owners are packages/occ/src/channel-secret-bindings.ts, drivers/channel/slack.ts, tests/integration/configuration-controller.test.mjs, and tests/conformance/slack-channel-directory.test.mjs.
- Upstream production composition passes expectProxy based on API egress policy. Teams' BundledChannelDriver constructor accepts only managedProxyHosts and constructs SlackChannelDriver with transport alone. Refresh must preserve the diagnostic behavior introduced by 7d02eb9b0 and 30af93be0.
- Console ownership changed upstream: 47e961ca7 and 72b3207da moved credential and channel behavior into .mts implementations; .mjs files now forward exports. Teams edits the older .mjs implementations. Port the additions into current owners while preserving Secret-operation checks, partial-save handling, and accepted Slack reference forms.
- Callback ownership is substantive: reconcileTeamsRoute at kubernetes/index.ts:12460 uses the serving Deployment's revision, exact POST path, separate hostname, preserved Microsoft Authorization, and stripped OCE identity headers. The retirement test at tests/conformance/kubernetes-compute.test.mjs:16002 covers predecessor preservation, cutover, and route-before-policy deletion using a Kubernetes fixture.
- Combination adaptation: outbound a50b14647 provides revision-owned gatewayNetworkRequirements through composition/channel.ts, currently for Slack. Embedded 94346f810 has separate reconcileTeamsCallback logic and revision-selected callback resources. These require coordinated provider requirements and callback ownership, not source-branch dependencies.
- Runtime packaging must retain upstream's Docker assembly and deploy/runtime/openclaw-source.json pin 554f0b886bde6c089578c49967227f8b50d1cf16 while adding msteams. Existing runtime-image-startup tests cover SDK callback rejection and guarded media; tests/fixtures/teams-attachment-download.mjs exercises real SDK transport with simulated DNS/connections, not live Microsoft delivery.
- Validation at Teams HEAD: CI manifest audit passed with no issues; syntax checks for Teams editor, directory UI, and proxy passed; git diff --check passed. teams-directory.test.mjs failed during import because @openclaw-enterprise/occ is unavailable: zero behavioral tests passed. No dependencies were installed, and no hosted CI, browser, cluster, or native-image pass is claimed. The worktree remained clean.

### embedded-adapt

Reviewed the independent embedded refresh and added missing Teams image-loading coverage. Existing upstream validation repairs remain intact; combination adaptations were not introduced.
- Extended the registered embedded runtime startup case to require Slack and Teams plugins with installed dependencies; documented its proof limits.
- Structural suite audit passed with no issues. Syntax, whitespace, and channel flow structure checks passed.
- Focused API and image tests failed during import because workspace dependencies are absent. Workspace and document checks also lacked dependencies; behavioral verification remains pending.
- Migration files and upstream runtime source pin remain unchanged. No Git or remote writes occurred.

### first-admin-adapt

Retained first-admin preparation and upstream improvements. Added five existing regression scenarios to required CI coverage in two suite manifests. No combination behavior, Git writes, or migration changes.
- Preserved security defaults, Agent naming, socket/audit handling, and managed-mode restrictions.
- Source audit passed with no issues; syntax and whitespace checks passed.
- Runtime tests could not load: typebox is missing. Workspace verification is blocked by missing prettier. No dependencies were installed.

### outbound-adapt

Retained the standalone outbound refresh and strengthened the owning API regression for both Gateway managed modes. No Git or remote writes.
- Proxy settings remain saveable; managed outbound admission rejects overrides. Coverage also permits the same Configuration without managed outbound.
- All 64 upstream migration files and journal entries are unchanged; all 65 candidate SQL hashes match.
- Suite-selection audit, syntax check, diff check, flow validation, and invalid-policy test passed.
- API, workspace, documentation, and control-plane CLI checks were blocked by missing dependencies. No dependencies were installed.
- PostgreSQL catalog qualification remains pending; catalogs.completed is null and migration execution remains fail-closed.

### plugins-adapt

Reviewed the prepared plugins refresh at 5521c0280 against frozen upstream. No additional edits or design decisions were needed. Runtime verification remains blocked by missing dependencies.
- Plugin-policy preservation and admission checks coexist with upstream Gateway validation, managed-mode handling, and Google Workspace behavior.
- Existing browser, REST, and PostgreSQL regressions remain registered; CI ownership audit passed.
- Syntax checks and git diff --check passed. Harness flow validation passed.
- REST tests could not load without typebox; workspace and document checks lacked prettier and @sindresorhus/slugify.
- Agent-creation flow validation reports a pre-existing upstream changelog-format failure.
- Migration history and upstream’s deleted breaking-changes page remain unchanged. Working tree is clean; no Git or remote writes occurred.

### profiles-adapt

Reviewed the prepared profiles refresh and extended custom-starter authorization regression coverage. No design decision or combination-specific changes were needed.
- Candidate already preserves upstream safeguards and includes the profile-file cleanup fix with alias collision coverage.
- Extended the existing browser denial test to cover custom starters, asserting HTTP 403, no Agent form, and no mutation requests after access revocation.
- Suite registration audit, syntax checks, both owning flow validators, and git diff --check passed.
- Browser and renderer tests failed during dependency loading; behavioral assertions did not run.
- Documentation and workspace checks were blocked by missing dependencies. PostgreSQL and Storybook prerequisites are unavailable; lint, formatting, and visual proof remain unverified.
- Only tests/browser/console-agent-presets.test.ts was edited. No Git mutations, remote writes, dependency installation, migration changes, or frozen check-policy changes occurred.

### roles-adapt

Completed source-level roles refresh fixes. Full runtime and PostgreSQL qualification remain outstanding.
- Fixed the runtime HTTP test’s missing ServerResponse import and corrected WebSocket denial fixtures to exercise assignment rejection with a managed identity.
- Updated all role-patch checksum consumers; patch application check passed.
- Runtime-assets tests passed: 2 tests, no skips. Suite-registration audit and git diff --check passed.
- All 65 frozen-upstream SQL files and the upstream journal prefix remain unchanged.
- API tests could not load @openclaw-enterprise/utils; workspace verification could not load prettier.
- The completed migration catalog remains unqualified and fails closed. Local PostgreSQL is 17.6; qualification requires 18.6.
- No commits, remote writes, dependency installation, or private combination adaptations were made.

### secrets-adapt

Retained the prepared Secrets adaptation and strengthened its owning regression to cover multiple distinct Configuration Secrets, partial grant failure, and retry without duplicates. No combination-specific behavior was added.
- Preserved saved-Configuration-derived exact grants and upstream validation and permission handling.
- Extended console-agent-presets.test.ts and updated its flow documentation; existing suite registration covers the scenario.
- Suite inventory audit, syntax checks, flow-document validation, and diff whitespace checks passed.
- Browser execution failed during module loading: @openclaw-enterprise/contracts is unavailable. Workspace and documentation checks also lack dependencies; runtime and visual proof remain unverified.
- pnpm attempted automatic reconciliation despite the required environment setting. All commands were interrupted, and generated artifacts were removed; no packages were downloaded or added.
- No migrations, Git state, remote resources, or frozen check policy were changed.

### teams-adapt

Completed standalone Teams refresh corrections, preserving upstream improvements. Fixed actionable deployment refusals and extended owning regression coverage.
- Teams admission now preserves its specific refusal through the API as HTTP 400 before creating an Agent revision.
- Extended existing conformance and API integration cases; both files are already registered in CI.
- Suite-registration audit, syntax checks, flow-document validation, and git diff --check passed.
- Admission tests could not load missing workspace packages; regression fail/pass comparison remains unverified.
- Proxy suite: 2 passed, 13 failed because sandbox permissions prohibit listening sockets; no skips.
- Workspace/document checks require missing dependencies. Lint, typecheck, browser, cluster, and native-image proof remain unavailable.
- Upstream migrations and runtime source pin remain unchanged. No Git mutations, remote writes, dependency installation, or private combination adaptations.

Execution tool source digests: `720c6d896abc9b3a4a1b59a5adbf09cfd1c2bf9456be581f3dc3b3ad9f76bcc0`

## Publication

{}

Checks prove their configured behavior. Detailed worker transcripts and raw logs remain local.
