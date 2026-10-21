# Prepare the public transition

Repository visibility and distribution are separate decisions. Keep this repository
private until an owner explicitly authorizes the transition. Do not dispatch CI,
commit, push, publish or rewrite history while the preparation hold is in effect.

## Execution and repository controls

Public pull requests run only offline contributor checks, with a read-only token
on GitHub-hosted runners. Credentialed integration and release jobs require the
private canonical repository; their raw logs and diagnostic artifacts may contain
sensitive data. A `private-` artifact name grants no access control. Moving source
to a public repository disables these jobs. Establish a separate private qualification
execution/storage boundary before resuming them, preserving exact commit, source,
image, workflow-run and destination checks. Keep generated customer assets subject
to the release allowlist.

The human-authored policies in `.github/policies/` define read-only workflow
defaults, pull-request and contributor-check requirements for main, and protection
against updates/deletion of release tags. Check their actual enforcement in GitHub;
source files do not apply settings by themselves. The contributor check must run
on the new workflow before a change can satisfy branch protection. History cleanup
requires a separately authorized, controlled exception to ref protection.

Keep secret scanning and push protection enabled. Before public access, verify
fork-run approval settings, and enable **Security → Report a vulnerability** as part
of the visibility transition; GitHub offers that reporting feature for public
repositories. Confirm maintainers can receive private reports. Follow
[the reporting policy](../SECURITY.md).

## Final clearance

- Verify Connections source and its exact selected package are accessible without
  RAW credentials. Public source alone does not change package-registry access.
  Update and test the resolver against the chosen public artifact channel.
- Review the intended publication tree and all retained Git refs with a secret
  scanner. Inspect releases, attachments, Actions runs/logs/artifacts and other
  repository metadata separately. Remove or sanitize unapproved historical material
  only after the owner authorizes that cleanup; deleting working files is insufficient.
- Retain required upstream copyright/license notices and confirm redistributable
  component contents. Apache-2.0 applies to RAW's original work.
- Commit and validate the reviewed tree only when the preparation hold is lifted.
  Check fresh-checkout contributor tests, anonymous dependency resolution and the
  intended public CI behavior. New distribution builds still need real native
  qualification and any selected upgrade proof.
- Recheck destination, privacy, identity and head immediately before the authorized
  transition. Source publication does not require publishing a new distribution version.

Current local resolved inputs may predate changed templates or examples. Do not
edit their inventories or reuse old receipts to qualify new inputs. Resolve a fresh
snapshot after the hold is lifted; preserve old snapshots only as private scratch.
