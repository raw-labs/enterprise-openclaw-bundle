// Check the packaged native extensions and record their addition to the runtime.
import { readFileSync, writeFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";

export function verifyPluginCompatibility(pkg, manifest, selected, hostVersion, semver) {
  if (pkg.name !== selected.package || pkg.version !== selected.version ||
      manifest.id !== selected.id || manifest.version !== selected.version) {
    throw new Error(`Native plugin identity mismatch: ${selected.id}`);
  }
  const sdk = pkg.openclaw?.build?.pluginSdkVersion;
  const api = pkg.openclaw?.compat?.pluginApi;
  // build.pluginSdkVersion records provenance; compat.pluginApi declares which
  // hosts can use it. Peer dependencies are npm metadata, not OCE admission.
  if (!semver.valid(hostVersion) || typeof sdk !== "string" || !semver.valid(sdk) ||
      (api === undefined ? sdk !== hostVersion :
        typeof api !== "string" || !api.trim() || api.includes("||") || !semver.validRange(api) ||
        !semver.satisfies(hostVersion, api) || !semver.satisfies(sdk, api))) {
    throw new Error(`Native plugin SDK compatibility mismatch: ${selected.id} on ${hostVersion}`);
  }
  for (const minimum of [pkg.openclaw?.compat?.minGatewayVersion, pkg.openclaw?.install?.minHostVersion]) {
    if (minimum !== undefined && (typeof minimum !== "string" || !semver.valid(minimum) || !semver.gte(hostVersion, minimum))) {
      throw new Error(`Native plugin requires a newer Gateway: ${selected.id}`);
    }
  }
}

function assemble() {
  const selected = JSON.parse(readFileSync("/tmp/bundle-plugins.json", "utf8"));
  const path = "/opt/oce/runtime/provenance.json";
  const provenance = JSON.parse(readFileSync(path, "utf8"));
  const openclaw = JSON.parse(readFileSync("/app/node_modules/openclaw/package.json", "utf8"));
  const semver = createRequire("/app/node_modules/openclaw/package.json")("semver");
  for (const plugin of selected) {
    const root = `/app/node_modules/openclaw/dist/extensions/${plugin.id}`;
    const pkg = JSON.parse(readFileSync(`${root}/package.json`, "utf8"));
    const manifest = JSON.parse(readFileSync(`${root}/openclaw.plugin.json`, "utf8"));
    verifyPluginCompatibility(pkg, manifest, plugin, openclaw.version, semver);
    for (const [file, expected] of Object.entries(plugin.files)) {
      if (createHash("sha256").update(readFileSync(`${root}/${file}`)).digest("hex") !== expected) {
        throw new Error(`Native plugin file mismatch: ${plugin.id}/${file}`);
      }
    }
  }
  provenance.plugins = [...provenance.plugins, ...selected.map(p => p.id)];
  provenance.pluginPackages = selected;
  writeFileSync(path, `${JSON.stringify(provenance, null, 2)}\n`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) assemble();
