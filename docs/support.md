# Support and lifecycle

Use the support contact and private channel established in your RAW Labs agreement.
Support eligibility, maintained versions, security backports, response times and
end-of-support dates are governed by that agreement. This repository does not
promise a support term or response time. Source availability and the Apache-2.0
license do not grant a commercial support entitlement.

Published release assets and tags identify an immutable distribution. Their
continued availability does not mean every historical release is actively
maintained. Prereleases are for evaluation unless your agreement explicitly
covers production use. Working definitions and locally generated packages remain
unqualified; passing local checks does not establish production support or customer
installation acceptance.

Before choosing or updating a production version, confirm coverage and the upgrade
path with your support contact. Preserve the current archive, checksum and recovery
material. Follow [the update procedure](update.md); a release with no recorded
upgrade baseline does not provide evidence of an upgrade from your current version.
Fixes use a new version rather than replacement assets.

For a support request, include the bundle version, archive checksum, operating
system/architecture, selected profile, failing command and a sanitized error.
Include the relevant component identity from `metadata/release.json` and whether
the problem occurs during verification, rendering, installation or runtime. Keep
site configuration, customer identifiers, credentials and raw logs in the
installation owner's protected workspace; arrange private transfer when needed.

Bundle maintainers own selection, packaging, verification and handoff. OCE owns
product behavior; plugin owners own provider integration behavior. Installation
owners own infrastructure, accounts, credentials, backups and live acceptance.
The support contact coordinates routing; customers need not disclose sensitive
details to upstream repositories. Report suspected vulnerabilities through
[the security procedure](../SECURITY.md).
