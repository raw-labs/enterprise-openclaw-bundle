# Components and responsibilities

This repository selects and verifies an installation kit for OpenClaw Enterprise
(OCE). It builds matching controller, Agent runtime and repository-credentials images,
and packages the chart, operator CLI, preparation tools and procedures. Images are
distributed separately by immutable digest.

OCE owns the product APIs, Console, authentication, tenancy, Agent lifecycle and
Kubernetes behavior. OpenClaw and Codex supply selected runtime components. Native
plugins add integrations; their providers still require installation-owned accounts
and credentials. Packaging a plugin does not establish provider access.

## Source layout

| Directory | Owner and purpose |
| --- | --- |
| `curation/oce/` | Versioned OCE maintenance recipe, worker guidance and candidate verification; no release publication. |
| `bundles/<version>/` | Maintained definitions, exact source selection, confinement pins and release-specific patches. |
| `presets/` | Agent templates selected by definition; they are seeded by OCE. |
| `profiles/` | Installation profiles selected by definition; they guide input rendering. |
| `scripts/` | Source resolution, builds, verification, packaging and publication mechanics. |
| `delivery/` | Small preparation/verification payload copied into a delivery package. |
| `tests/unit/` | Offline validator and rejection checks using explicitly synthetic inputs. |
| `tests/integration/` | Packaging checks against exact resolved source, dependencies and CLI binaries. |
| `tests/` | Native image/plugin checks and disposable package-installation tests. |
| `docs/` | Procedures and generic installation examples. |

`presets/` and `profiles/` contain ingredients, not automatic defaults. Read the
chosen definition to see which ones it selects. Retain bytes referenced by maintained
definitions; use new filenames when maintained selections need different contents.
Retired definitions and ingredients remain at their original source tags.

## Delivery layout

The downloaded archive has `INSTALL.md`, `UPDATE.md`, `OPERATE.md`, `SUPPORT.md`,
`SECURITY.md`, an operator-facing `AGENTS.md`, `bin/occ` and `bin/prepare`.
`oce/` preserves upstream chart/helper paths;
`defaults/` holds the delivered installation profile, `security/` contains selected
seccomp policies, `lib/` contains support code and CLI binaries, and `metadata/`
records the selected sources, images and checksums. `notices/` preserves bundle and
component license notices. Source and delivery layouts are
different: repository documentation links are adapted during packaging.

`occ` is the matched OCE operator CLI. `bin/prepare` only verifies a package and
renders/checks inputs. Installation owners provision infrastructure and credentials,
review generated files and deploy using OCE's procedures.

## Verification boundaries

Resolution produces an unqualified candidate. Packaging checks establish archive
contents and rendering behavior. Native release checks bind actual AMD64 and ARM64
shipping images to their source and reviewed confinement inputs. They do not qualify
customer infrastructure, real provider access or a customer's Agent workload.

Follow [contributor setup](../CONTRIBUTING.md) for local checks,
[release preparation](release.md) for maintainers, and the selected archive's
`INSTALL.md` for installation. Download/access instructions are in
[distribution](distribution.md).
