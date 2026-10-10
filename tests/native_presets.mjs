import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import test from "node:test";

test("selected RAW presets are image-resident and accepted by OCE's real loader", () => {
  const release = JSON.parse(readFileSync(process.env.BUNDLE_TEST_SELECTION, "utf8"));
  const sourceFiles = JSON.parse(readFileSync(resolve(dirname(process.env.BUNDLE_TEST_SELECTION), release.sources.oce.files), "utf8"));
  const consoleFiles = Object.fromEntries(["presets.mjs", "starter-model.mjs"].map(name => {
    const path = "apps/controller/src/console/agents/" + name;
    return [path, sourceFiles[path]];
  }));
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
    const includeDefaults = ${JSON.stringify(release.includeDefaultPresets ?? true)};
    const loaded = await loadInstallationPresets({presets: {includeDefaults, files: presets.map(p => p.path)}}, '/installation.yaml');
    for (const preset of presets) assert.ok(loaded.defaultPresets.some(p => p.name === preset.name));
    if (!includeDefaults) {
      assert.deepEqual(loaded.defaultPresets.map(p => p.name), presets.map(p => p.name));
      // Console behavior belongs to OCE's browser suite; ship its exact reviewed code.
      for (const [path, expected] of Object.entries(${JSON.stringify(consoleFiles)})) {
        assert.equal(createHash('sha256').update(await readFile('/app/' + path)).digest('hex'), expected);
      }
      for (const preset of loaded.defaultPresets) {
        const {values, secretBindings} = preset.template.configuration;
        assert.deepEqual(secretBindings, {});
        assert.deepEqual(preset.template.agent.plugins, {});
        assert.equal(values.gateway.controlUi.experimental.customPlugins, true);
        const connections = values.plugins.entries['openclaw-connections'];
        assert.equal(connections.enabled, true);
        assert.deepEqual(connections.config, {});
        for (const tool of ['connections_search','connections_describe','connections_call'])
          assert.ok(values.tools.alsoAllow.includes(tool));
        assert.equal(values.agents.defaults.thinkingDefault, 'medium');
        assert.equal(values.browser.enabled, false);
        assert.equal(values.tools.elevated.enabled, false);
        if (preset.template.agent.executionMode === 'dedicated') {
          assert.equal(values.plugins.entries.codex.enabled, true);
          const appServer = values.plugins.entries.codex.config.appServer;
          assert.equal(appServer.approvalPolicy, 'never');
          assert.equal(appServer.sandbox, 'workspace-write');
          assert.equal(appServer.networkProxy.mode, 'full');
          assert.deepEqual(appServer.networkProxy.domains, {'*':'allow'});
          assert.equal(values.agents.defaults.models[values.agents.defaults.model].agentRuntime.id, 'codex');
        } else {
          assert.equal(preset.template.agent.executionMode, 'embedded');
          assert.equal(values.agents.defaults.models[values.agents.defaults.model].agentRuntime.id, 'openclaw');
        }
        assert.equal(values.tools.web.fetch.enabled, true);
      }
    }
    await assert.rejects(loadInstallationPresets({presets: {files: ['/missing-preset.json']}}, '/installation.yaml'));
  `;
  execFileSync("docker", ["run", "--rm", "--network", "none", "--read-only", "--user", "1000:1000",
    "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--entrypoint", "node",
    process.env.OCC_TEST_PRODUCTION_IMAGE, "--input-type=module", "-e", script], {stdio: "pipe", timeout: 60_000});
});
