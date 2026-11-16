This release adds verified bundle downloads, site overrides for rendering, and
a read-only target check before installation or upgrade.

Use the bundle's `fetch.py` and `bin/prepare` in place of site-local copies.
Rerender from site inputs rather than editing generated Helm values or
Installation files. For an upgrade, retain the live values and Installation
and follow `UPDATE.md`.
