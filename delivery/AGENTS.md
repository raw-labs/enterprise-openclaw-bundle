This is RAW's curated installation kit for OpenClaw Enterprise (OCE).
It contains a matching chart, operator CLI, installation helpers,
templates and documentation. Container images are pulled separately
using the digests recorded in `metadata/release.json`.

Start with [INSTALL.md](INSTALL.md) for installation and
[OPERATE.md](OPERATE.md) for maintenance. Commands are in `bin/`;
packaged OCE tools and documentation are in `oce/`.
OCE defines product behavior and operational procedures.
The installation owner provides infrastructure and site-specific settings.
Keep site settings, generated configuration and credentials outside
this package directory.
