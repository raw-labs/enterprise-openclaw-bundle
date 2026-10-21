# License scope and upstream notices

Original RAW Labs code, documentation and configuration in this repository are
licensed under the [Apache License, Version 2.0](LICENSE), unless a file identifies
another license. Attribution for RAW's work is in [NOTICE](NOTICE).

This license applies to RAW's original contributions. It does not replace the
licenses or copyright notices on upstream or third-party material, including
upstream-derived portions of patches and adapted templates.

## OCE and adapted material

OCE material in source patches and adapted templates retains its MIT license and
attribution. An unchanged copy is in [LICENSES/OCE-MIT.txt](LICENSES/OCE-MIT.txt).
Original RAW additions are covered by Apache-2.0 while preserving those upstream
terms. Selecting or packaging upstream software does not relicense it.

Delivery packages retain the selected OCE license in `notices/OCE-LICENSE` and in
the chart. The matched `occ` binaries, upstream helpers, documentation and profiles
remain subject to their upstream licenses. Images retain OCE's license under
`/usr/share/licenses/openclaw-enterprise/`.

## Plugins and dependencies

OpenClaw, Codex, native plugins, base images and dependencies retain their own
licenses and notices. Plugin packages must carry `LICENSE`, `NOTICE` and
`THIRD_PARTY_NOTICES.md`; the factory preserves their bytes in the native extension.
Packaged renderer dependencies retain their license files beside their code.
Component identities and file inventories are recorded in generated release metadata.

## RAW notices in delivery

The Apache license, RAW notice, this scope document and the OCE MIT attribution copy
are included under `notices/` in delivery packages and under
`/usr/share/licenses/enterprise-openclaw-bundle/` in newly built images. These notices
accompany RAW's code and templates alongside the existing component notices.
