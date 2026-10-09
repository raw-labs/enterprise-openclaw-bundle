import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import test from "node:test";

test("selected RAW presets are image-resident and accepted by OCE's real loader", () => {
  const release = JSON.parse(readFileSync(process.env.BUNDLE_TEST_SELECTION, "utf8"));
  const script = `
    import assert from 'node:assert/strict';
    import { readFile } from 'node:fs/promises';
    import { createHash } from 'node:crypto';
    import { loadInstallationPresets } from '/app/apps/controller/src/composition/installation-presets.ts';
    const presets = ${JSON.stringify(release.presets ?? [])};
    for (const preset of presets) {
      const bytes = await readFile(preset.path);
      assert.equal(createHash('sha256').update(bytes).digest('hex'), preset.sha256);
    }
    const loaded = await loadInstallationPresets({presets: {includeDefaults: true, files: presets.map(p => p.path)}}, '/installation.yaml');
    for (const preset of presets) assert.ok(loaded.defaultPresets.some(p => p.name === preset.name));
    await assert.rejects(loadInstallationPresets({presets: {files: ['/missing-preset.json']}}, '/installation.yaml'));
  `;
  execFileSync("docker", ["run", "--rm", "--network", "none", "--read-only", "--user", "1000:1000",
    "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--entrypoint", "node",
    process.env.OCC_TEST_PRODUCTION_IMAGE, "--input-type=module", "-e", script], {stdio: "pipe", timeout: 60_000});
});
