# Report a security issue privately

On a public repository, use **Security → Report a vulnerability** when that button
is available. Reports through that feature are private. Customers can also use
the private support channel established with their RAW Labs contact or agreement;
collaborators can contact repository administrators through an existing private
channel.

If you have no private contact and reporting is unavailable, open an issue asking
only for a private reporting route, without vulnerability details. Do not post a
reproduction, affected customer identities, logs or exploit information. Wait for
private reporting instructions before sharing them. Private vulnerability reporting
must be enabled as part of the public transition; this policy does not claim it
is enabled while the repository remains private.

Include the bundle version, affected component and source identity from
`metadata/release.json`, platform, impact and minimal reproduction steps. Describe
required permissions and whether a workaround is known. Send only sanitized
evidence initially; arrange a protected transfer before sharing sensitive material.
Never include credentials, customer identifiers, kubeconfigs, Secret exports or
raw workload logs in repository submissions.

Maintainers triage the report privately, coordinate with the affected upstream
owner and agree on remediation and disclosure through the reporting channel.
Response commitments and maintained versions follow the applicable support
agreement; see [support and lifecycle](docs/support.md). A downloadable release
does not by itself imply active maintenance.

Keep the affected archive and its checksum for investigation. Corrections ship as
new immutable releases; do not replace evidence or edit a package manifest to make
verification pass. Installation owners control containment, credential rotation
and live remediation under their own incident procedures.
