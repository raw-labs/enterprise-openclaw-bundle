# Review and ownership

Repository maintainers own release selection, factory mechanics, package
verification and customer handoff. Use repository access records to identify
current maintainers. Product changes belong in OCE; plugin changes belong with
their owners. Installation owners control infrastructure, accounts and live
Agents. See the [component map](overview.md).

## Review a change

A maintainer reviews changes before merging. A sole maintainer may review and
merge their own changes; no second approver is required. Review security,
confinement, licensing and release changes with particular care, seeking relevant
expertise when needed. Branch rules are configured separately in GitHub.

- Selection changes: inspect exact commits, package identities, hashes, patches
  and license notices. New ingredients and changed templates start unqualified.
- Factory and delivery changes: cover rejection of invalid inputs, changed or
  extra files, links, source/image mismatches and unintended output contents.
- Documentation changes: verify repository links and the delivered links and
  commands. Keep site identities and current qualification claims out of prose.
- Release changes: inspect workflow permissions, authorized destinations and visibility, attachment
  allowlists and provenance binding. Keep raw diagnostics and build inputs out of
  customer assets.

Run [contributor checks](../CONTRIBUTING.md) and report what ran. Prepared-source
integration checks must use real charts and matched binaries, with deterministic
archives. Local fixtures do not substitute for native runtime qualification.

## Review a release

Follow the [release procedure](release.md). Confirm identity, authorized repository visibility,
origin and expected remote head before pushing or publishing. Stop on an
unexpected destination or head. Native AMD64 and ARM64 evidence must match the
selected inputs and exact shipping artifacts, with reviewed confinement and no
skipped tests. Check package installation evidence and any selected upgrade
baseline. Provider access and installation acceptance remain the owner's work.

Use a fresh handoff output directory. Only the documented release assets may be
present, and every asset other than provenance must match its recorded checksum.
Do not add ad hoc files to make an upload convenient. Changing the allowlist is a
reviewed factory change with rejection coverage. Never replace historical tags,
receipts or assets as routine release recovery.

Route vulnerability reports through [the private security procedure](../SECURITY.md).
Support and maintenance commitments follow [the support policy](support.md).
