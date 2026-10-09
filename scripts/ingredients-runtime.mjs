// Check the packaged native extensions and record their addition to the runtime.
import { readFileSync, writeFileSync } from "node:fs";
import { createHash } from "node:crypto";
const selected = JSON.parse(readFileSync("/tmp/bundle-plugins.json", "utf8"));
const path = "/opt/oce/runtime/provenance.json";
const provenance = JSON.parse(readFileSync(path, "utf8"));
for (const plugin of selected) {
  const root = `/app/node_modules/openclaw/dist/extensions/${plugin.id}`;
  const pkg = JSON.parse(readFileSync(`${root}/package.json`, "utf8"));
  const manifest = JSON.parse(readFileSync(`${root}/openclaw.plugin.json`, "utf8"));
  const openclaw = JSON.parse(readFileSync("/app/node_modules/openclaw/package.json", "utf8"));
  if (pkg.name !== plugin.package || pkg.version !== plugin.version || manifest.id !== plugin.id ||
      pkg.openclaw.build.pluginSdkVersion !== openclaw.version) {
    throw new Error("Native plugin identity or SDK mismatch.");
  }
  for (const [file, expected] of Object.entries(plugin.files)) {
    if (createHash("sha256").update(readFileSync(`${root}/${file}`)).digest("hex") !== expected) {
      throw new Error(`Native plugin file mismatch: ${plugin.id}/${file}`);
    }
  }
}
provenance.plugins = [...provenance.plugins, ...selected.map(p => p.id)];
provenance.pluginPackages = selected;
writeFileSync(path, `${JSON.stringify(provenance, null, 2)}\n`);
