# Operate an installation

For installation owners. OCE owns operational behavior; the bundle supplies
matching artifacts and exact-source tools. Run OCE procedures from `oce/`.

## Accept and retain

Keep the downloaded archive/checksum, site inputs, generated configuration,
image/mirror selection and Helm release identity. Protect credentials and
database/PV backups according to the installation's recovery policy.

Before handoff, verify image pulls, authenticated `occ installation get`, Console
sign-in, Namespace readiness, a real Agent/model turn, workspace persistence,
access restrictions and confinement on the actual nodes. Test enabled plugins,
repository access and external identity providers separately. Bundle artifact
checks do not establish acceptance of a customer's environment.

## Presets and native plugins

OCE seeds selected presets when it starts and when a Namespace is created.
Existing same-name presets are preserved, including operator edits; changed
bundle templates do not automatically replace them.

The selected Assistant and Coding presets enable Connections and native plugin UI.
The default shortcut chooses a readable `default-codex` if retained; otherwise it
chooses the first readable preset alphabetically. A fresh two-preset installation
therefore starts with Assistant. **Reset template** uses OCE's generic starter;
choose a preset again to restore its curated settings.

Other selected native plugins are already in the runtime image. Enable them through
OCE's [native Configuration values and Secret bindings](oce/docs/reference/configuration/secrets.md).
Configure `plugins.entries`; if an existing `plugins.allow` restricts loading, add
the plugin ID to that list.

## Connections

Without a project key, Connections reports configuration required and exposes no
tools. Native UI consent and administrator authentication still apply. Follow the
[plugin's provider setup](https://github.com/raw-labs/openclaw-connections#install-and-configure);
skip its package-install step. The Console's model password input cannot configure
plugin credentials.

An unresolved SecretRef keeps the Gateway and Connections UI available, but
management requests report `SECRET_SURFACE_UNAVAILABLE` and provider tools stay
inactive. Check the Secret binding and exact permissions. This differs from an
omitted key's unconfigured state; native secret-provider policy denial can still
reject Gateway startup.

For each Namespace, an installation owner:

1. Creates an OCE Secret from a protected JSON file with `occ secret create --file FILE`.
2. Grants each intended Agent creator exact `operate` permission on that Secret,
   using a Namespace Role and exact-resource AccessBinding. Preset read access
   does not grant Secret access. See OCE's [IAM procedure](oce/docs/guides/topics/iam.md).
3. Gets each installed preset with `occ preset get ID -o json`, preserves its
   template, and merges the following native configuration. Submit `{ "template":
   MODIFIED_TEMPLATE }` to `PATCH /namespaces/NAMESPACE_ID/presets/PRESET_ID` through
   the [authenticated HTTP API](oce/docs/guides/http-api.md). This requires exact
   preset `update`; the CLI does not implement preset updates.

```json
{
  "values": {
    "plugins": {
      "entries": {
        "openclaw-connections": {
          "enabled": true,
          "config": {
            "apiKey": {
              "source": "env", "provider": "default", "id": "COMPOSIO_API_KEY"
            }
          }
        }
      }
    }
  },
  "secretBindings": {
    "COMPOSIO_API_KEY": {
      "source": { "kind": "secret", "namespaceId": "NAMESPACE_ID", "id": "SECRET_ID" },
      "delivery": { "type": "env" }
    }
  }
}
```

Merge this into `template.configuration`; retain its other values and bindings.
Omit `userId` so each Gateway retains its own Composio identity.
Stored templates contain references only; keep keys and customer IDs in protected
installation files. Future Agents inherit the binding; existing drafts do not.

Dedicated provisioning and Console Agent creation grant the new Agent principal
exact Secret `operate` access for accepted Configuration bindings. The Console
caller needs permission to create those IAM grants. If a grant fails, retain the
saved Agent and retry credential access or ask an administrator to complete it.
For Agents created directly through the API or CLI, grant `servicePrincipalId`
exact `operate` on each bound Secret before deployment. Use
`occ iam role create --file FILE` and `occ iam access-binding create --file FILE`;
verify the exact Namespace, Secret, principal and Role.

Each OCE Agent has its own Gateway Connections page, accounts and grants; the shared
project credential does not create a central account list. Administrators link
provider accounts and grant their use there. The complete Connections directory
uses that Gateway's private claim. Verify provider access, consent and retained
state in the installation; fixture checks do not prove external OAuth or execution.

## Diagnose

From the bundle root, run `bin/prepare verify` and
`bin/prepare check --directory "$SITE/rendered"`.
These check local files and chart rendering. Use OCE's procedures and ordinary
kubectl/Helm commands for cluster health; retain diagnostic logs privately.

## Upgrade and recover

Start with [UPDATE.md](UPDATE.md). For an interrupted update, retain its evidence
and maintenance restrictions and follow OCE's
[recovery procedure](oce/docs/guides/deploy/production-upgrade-recovery.md).
