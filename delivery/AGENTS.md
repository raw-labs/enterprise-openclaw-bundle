This is RAW's curated installation kit for OpenClaw Enterprise (OCE).
It pairs OCE's chart and tools with selected presets and native plugins.
Container images are downloaded separately by digest.

- [INSTALL.md](INSTALL.md): install into prepared Kubernetes infrastructure.
- [UPDATE.md](UPDATE.md): update an existing installation using OCE's procedure.
- [OPERATE.md](OPERATE.md): acceptance, diagnostics, presets and plugin configuration.
- [SUPPORT.md](SUPPORT.md): lifecycle, coverage and support requests.
- [SECURITY.md](SECURITY.md): private security reporting.
- [metadata/release.json](metadata/release.json): exact sources, images, ingredients and native artifact checks.
- [metadata/manifest.json](metadata/manifest.json): packaged file checksums; check with `bin/prepare verify`.
- [License scope and upstream notices](notices/THIRD_PARTY_NOTICES.md): RAW's Apache-2.0 license and preserved component notices.
- `bin/prepare`: verify this kit and render/check OCE inputs. `bin/occ`: matched upstream operator CLI.
- `oce/`: packaged OCE chart, helpers and product documentation. OCE owns operational behavior.
- Keep infrastructure, site settings, generated files and credentials outside this package. Its owner controls deployment and live changes.
