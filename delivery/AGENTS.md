This is RAW's curated installation kit for OpenClaw Enterprise (OCE).
It contains a matching chart, operator CLI, installation helpers,
selected presets and documentation. Container images are pulled separately
using the digests recorded in `metadata/release.json`.

Start with [INSTALL.md](INSTALL.md) for installation and
[OPERATE.md](OPERATE.md) for maintenance. Commands are in `bin/`;
packaged OCE tools and documentation are in `oce/`.
OCE defines product behavior and operational procedures.
Selected RAW presets are seeded by OCE; native plugins are packaged in the runtime
and configured through OCE. Preset files in the kit are for inspection.
The installation owner provides infrastructure and site-specific settings.
Keep site settings, generated configuration and credentials outside
this package directory.
