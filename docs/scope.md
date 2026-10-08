# Scope and ownership

Each selection in `release.json` owns its limitations and evidence. New stock
candidates are unqualified until their final artifacts are reviewed. The recorded
baseline is portable packaging of the internal AWS pilot, suitable for an explicitly
accepted evaluation in another installation after access and prerequisites are
prepared. It is not a customer-qualified product release. Pending OCE changes
must be delivered as a new exact input and independently qualified.

| Owner | Responsibility |
| --- | --- |
| OCE integration | Exact combined OCE commit; controller/runtime recipes, OC patches, chart and compatible fixtures |
| OpenClaw | Runtime source and extensions; included through OCE's pinned recipe |
| This bundle | Source selection, stock build recipes, historical overlay, packaging, image qualification and private delivery |
| Installation operator | Cluster, cloud account, DNS/TLS, database roles, node policy, registry pulls, Secrets, users, Agents, repository grants, backups and restore testing |
| Sales engineer | Obtain authorized artifacts, prepare customer inputs, run the installation checks and record acceptance |

The unchanged OCE chart installs the control plane, migration/bootstrap hooks,
private routing and optional repository credential sidecar. Cert-manager, Gateway
API/Envoy, policy enforcement, storage, database and public ingress are prerequisites,
not a second chart. AWS is the recorded pilot profile. A future Azure profile can
supply the same installation input contract and its own prerequisite qualification;
there is no Azure infrastructure implementation or tested Azure support here.

The runtime serves both gateway and dedicated harness slots. Execution mode is
chosen per Agent. Optional Coding and Assistant templates were derived from authored
pilot templates, not release receipts; they configure Agents and do not alter images.
Coding uses dedicated Codex with an API-key Secret; Assistant uses embedded OC.
They start with loopback UI origins; add each deployed Agent's exact HTTPS origin
through its OCE Configuration before using native UI. Model credentials, native
GitHub App repository access and personal ChatGPT OAuth are different mechanisms.
The packaged curated catalog override avoids hosted catalog discovery credentials;
the generated preflight replaces hosted/PAT advisories with per-Agent credential requirements.

Import optional templates using the authenticated OCE Namespace preset API
(`POST /namespaces/<id>/presets`, JSON file as body) or use OCE's seeded templates.
Create Agent-owned Secrets and grant access in the Console. Runtime plugins,
OC extensions, channels and remote MCP endpoints have different contracts. The
baseline does not qualify Notion or imply that a Codex plugin is an OC extension.

Tenant RBAC manifests are supplemental, generated only for an explicit OCE Namespace
ID. Optional public TCP egress requires an explicit Agent ID and review; it excludes
private/reserved IPv4 but permits access to public services. It does not replace
Codex proxy policy or prove isolation on the customer's CNI. Repository integration
uses the selected OCE service and requires customer-owned App/TLS/registry inputs;
start with it disabled and use the bundled upstream service procedure after bootstrap.
Its links resolve to public upstream material at the selected source revision.

Only supported mounts persist (including workspaces, configured auth/home paths and
bootstrap output); the full container filesystem does not. OCE-rendered configuration
can replace UI edits on redeploy. Installation-owned backup/restore policy must cover
database, persistent volumes and private credential recovery. Pilot backup settings
are not inherited.

Private build source remains private, while delivered charts carry OCE's MIT notice
and runtime images retain upstream licenses/notices and inventory. Shipped code is
visible to its recipient, including any future private plugin code in an image.
Connections must eventually supply its own pinned artifact; it is excluded now.
