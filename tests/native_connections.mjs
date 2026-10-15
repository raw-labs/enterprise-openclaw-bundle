// Real shipping image and Kubernetes volume checks; no external provider calls.
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { randomBytes } from "node:crypto";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import test from "node:test";
import { pathToFileURL } from "node:url";

const release = JSON.parse(await readFile(process.env.BUNDLE_TEST_SELECTION, "utf8"));
const plugins = release.pluginPackages ?? [];
const image = process.env.OCC_TEST_RUNTIME_IMAGE;

test("packaged native extensions and their inventory match the selected release", () => {
  const script = `
    const assert = require('node:assert/strict'), fs = require('node:fs'), crypto = require('node:crypto');
    const selected = ${JSON.stringify(plugins)};
    const provenance = JSON.parse(fs.readFileSync('/opt/oce/runtime/provenance.json'));
    const contents = fs.readFileSync('/opt/oce/runtime/contents.json');
    assert.equal(crypto.createHash('sha256').update(contents).digest('hex'), provenance.runtimeContentsSha256);
    const inventory = JSON.parse(contents);
    if (selected.length) assert.deepEqual(provenance.pluginPackages, selected);
    for (const plugin of selected) {
      assert.ok(provenance.plugins.includes(plugin.id));
      for (const [file, expected] of Object.entries(plugin.files)) {
        const path = 'dist/extensions/' + plugin.id + '/' + file;
        assert.equal(crypto.createHash('sha256').update(fs.readFileSync('/app/node_modules/openclaw/' + path)).digest('hex'), expected);
        assert.equal(inventory.find(p => p.path === path)?.sha256, expected);
      }
    }
  `;
  execFileSync("docker", ["run", "--rm", "--network", "none", "--read-only", "--user", "1000:1000",
    "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--entrypoint", "node", image, "-e", script],
  {stdio: "pipe", timeout: 60_000});
});

test("Connections loads in the native Gateway and retains state across Kubernetes Pod replacement", {timeout: 600_000}, async () => {
  if (!plugins.some(p => p.id === "openclaw-connections")) return;
  const { KubernetesComputeDriver } = await import(pathToFileURL(resolve("apps/controller/src/drivers/compute/kubernetes/index.ts")));
  const driver = Object.create(KubernetesComputeDriver.prototype);
  driver.options = {runtime: {gatewayStorageClassName: "local-path"}};
  const mounts = driver.gatewayPrivateStateVolumeMounts(true);
  const stateDirectory = "/home/node/.openclaw/state";
  assert.deepEqual(mounts.find(m => m.subPath === "state"), {
    name: "openclaw-gateway-state", mountPath: stateDirectory, subPath: "state", readOnly: false,
  });
  const suffix = randomBytes(6).toString("hex");
  const cluster = "bundle-connections-" + suffix;
  const tag = "localhost/bundle-connections:" + suffix;
  const previousImage = process.env.BUNDLE_UPGRADE_RUNTIME_IMAGE;
  assert.equal(Boolean(previousImage), Boolean(release.upgradeBaseline), "selected runtime upgrade baseline is required");
  const previousTag = "localhost/bundle-connections-previous:" + suffix;
  const directory = await mkdtemp(join(tmpdir(), cluster + "-"));
  const kubeconfig = join(directory, "kubeconfig");
  const run = (command, args, options = {}) => execFileSync(command, args, {encoding: "utf8", timeout: 180_000, maxBuffer: 4 * 1024 * 1024, ...options});
  const kube = (...args) => run("kubectl", ["--kubeconfig", kubeconfig, "--context", "k3d-" + cluster, "-n", "bundle-connections", ...args]);
  function put(object) {
    return run("kubectl", ["--kubeconfig", kubeconfig, "--context", "k3d-" + cluster, "apply", "-f", "-"], {input: JSON.stringify(object)});
  }
  const token = "synthetic-bundle-gateway-token";
  let config = {
    gateway: {mode: "local", bind: "loopback", port: 18789, auth: {mode: "token", token}, controlUi: {experimental: {customPlugins: true}}},
    plugins: {allow: ["openclaw-connections"], slots: {memory: "none"}, entries: {
      "openclaw-connections": {enabled: true, config: {apiKey: {source: "env", provider: "default", id: "COMPOSIO_API_KEY"}}},
    }},
  };
  const configuredBase = structuredClone(config);
  const pod = {
    apiVersion: "v1", kind: "Pod", metadata: {name: "gateway", namespace: "bundle-connections"},
    spec: {
      automountServiceAccountToken: false, restartPolicy: "Never", terminationGracePeriodSeconds: 120,
      securityContext: {runAsUser: 1000, runAsGroup: 1000, runAsNonRoot: true, fsGroup: 1000, seccompProfile: {type: "RuntimeDefault"}},
      initContainers: [driver.privateStateInitContainer("gateway", tag, true)],
      containers: [{
        name: "gateway", image: tag, imagePullPolicy: "Never", command: ["node", "/app/openclaw.mjs", "gateway", "run"],
        securityContext: {allowPrivilegeEscalation: false, readOnlyRootFilesystem: true, capabilities: {drop: ["ALL"]}},
        env: [{name: "OPENCLAW_STATE_DIR", value: "/home/node/.openclaw"}, {name: "OPENCLAW_CONFIG_PATH", value: "/config/openclaw.json"},
          {name: "OPENCLAW_NO_AUTO_UPDATE", value: "1"}, {name: "COMPOSIO_API_KEY", value: "synthetic-never-sent-project-key"}],
        volumeMounts: [
          {name: "runtime-state", mountPath: "/home/node", subPath: "home"},
          {name: "runtime-temporary", mountPath: "/tmp", subPath: "tmp"},
          {name: "config", mountPath: "/config", readOnly: true}, ...mounts,
        ],
        readinessProbe: {exec: {command: ["node", "-e", "fetch('http://127.0.0.1:18789/readyz').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"]}, periodSeconds: 2},
      }],
      volumes: [{name: "runtime-state", emptyDir: {}}, {name: "runtime-temporary", emptyDir: {}},
        {name: "config", configMap: {name: "gateway"}}, {name: "openclaw-gateway-state", persistentVolumeClaim: {claimName: "gateway"}}],
    },
  };
  const native = (...args) => kube("exec", "gateway", "-c", "gateway", "--", "node", "/app/openclaw.mjs", ...args);
  const call = (method, params = {}) => {
    try {
      return JSON.parse(native("gateway", "call", method, "--url", "ws://127.0.0.1:18789", "--token", token, "--params", JSON.stringify(params), "--json"));
    } catch (error) {
      throw new Error([error.message, error.stdout, error.stderr].filter(Boolean).join("\n"), {cause: error});
    }
  };
  const start = () => {put(pod); kube("wait", "--for=condition=Ready", "pod/gateway", "--timeout=180s");};
  const stop = () => kube("delete", "pod/gateway", "--wait=true", "--timeout=180s");
  let created = false;
  let tagged = false;
  let previousTagged = false;
  let phase = "create disposable cluster";
  try {
    run("docker", ["tag", image, tag]);
    tagged = true;
    if (previousImage) {
      run("docker", ["tag", previousImage, previousTag]);
      previousTagged = true;
    }
    run("k3d", ["cluster", "create", cluster, "--servers", "1", "--agents", "0", "--no-lb", "--image",
      "docker.io/rancher/k3s:v1.35.9-k3s1@sha256:ec9868c6a38d4e8c1869832fb5fd1eb8473c39794a0b44d2b952e7ba911951bc",
      "--kubeconfig-update-default=false", "--kubeconfig-switch-context=false", "--wait"]);
    created = true;
    await import("node:fs/promises").then(fs => fs.writeFile(kubeconfig, run("k3d", ["kubeconfig", "get", cluster]), {mode: 0o600}));
    run("k3d", ["image", "import", tag, "--cluster", cluster], {timeout: 240_000});
    if (previousImage) {
      run("k3d", ["image", "import", previousTag, "--cluster", cluster], {timeout: 240_000});
    }
    put({apiVersion: "v1", kind: "Namespace", metadata: {name: "bundle-connections"}});
    put({apiVersion: "v1", kind: "PersistentVolumeClaim", metadata: {name: "gateway", namespace: "bundle-connections"}, spec: {
      accessModes: ["ReadWriteOnce"], storageClassName: "local-path", resources: {requests: {storage: "100Mi"}},
    }});
    const saveConfig = () => put({apiVersion: "v1", kind: "ConfigMap", metadata: {name: "gateway", namespace: "bundle-connections"}, data: {"openclaw.json": JSON.stringify(config)}});
    const uiAvailable = () => {
      assert.ok(call("plugins.controlUi.list").plugins.some(p => p.pluginId === "openclaw-connections"));
      if (config.gateway.controlUi?.communityInvite === false) {
        kube("exec", "gateway", "-c", "gateway", "--", "node", "--input-type=module", "-e", `
          import assert from 'node:assert/strict';
          const response = await fetch('http://127.0.0.1:18789/control-ui-config.json', {
            headers: {authorization:'Bearer ${token}'}});
          assert.equal(response.status,200);
          assert.equal((await response.json()).communityInvite,false);
        `);
      }
    };
    const selectedConfig = async (preset) => {
      assert.ok(preset.path.startsWith("/app/"));
      const selected = JSON.parse(await readFile(resolve(preset.path.slice(5)), "utf8"));
      const values = JSON.parse(JSON.stringify(selected.template.configuration.values).replaceAll("{{ vars.model }}", selected.template.variables.model.default));
      values.gateway = {...values.gateway, bind:"loopback", port:18789, auth:{mode:"token",token}};
      values.plugins.slots = {memory:"none"};
      return values;
    };
    const noTools = () => kube("exec", "gateway", "-c", "gateway", "--", "node", "--input-type=module", "-e", `
      import assert from 'node:assert/strict';
      for (const name of ['connections_search','connections_describe','connections_call']) {
        const response = await fetch('http://127.0.0.1:18789/tools/invoke', {method:'POST',
          headers:{authorization:'Bearer ${token}','content-type':'application/json'},
          body:JSON.stringify({tool:name,args:{},agentId:'main',idempotencyKey:'unconfigured-'+name})});
        assert.equal(response.status,404); assert.match(await response.text(),/Tool not available/);
      }
    `);
    if (release.includeDefaultPresets === false) {
      pod.spec.containers[0].env = pod.spec.containers[0].env.filter(e => e.name !== "COMPOSIO_API_KEY");
      pod.spec.containers[0].env.push({name:"APP_SERVER_URL",value:"ws://127.0.0.1:9"}, {name:"APP_SERVER_TOKEN",value:"synthetic-guardian-token"});
      for (const preset of release.presets) {
        config = await selectedConfig(preset);
        phase = "unconfigured selected preset " + preset.name;
        saveConfig(); start();
        if (config.plugins.entries["openclaw-connections"]?.enabled === true) {
          assert.deepEqual(call("connections.status"), {configured:false,userId:null});
          uiAvailable();
        } else {
          assert.throws(() => call("connections.status"), /unknown method|not found|not registered/i);
        }
        noTools();
        if (config.browser?.enabled) {
          phase = "Assistant headless browser in the confined runtime";
          assert.equal(call("browser.request", {target:"host", method:"POST", path:"/start", query:{profile:"openclaw"}}).ok, true);
          const status = call("browser.request", {target:"host", method:"GET", path:"/", query:{profile:"openclaw"}});
          assert.equal(status.running, true);
          const tab = call("browser.request", {target:"host", method:"POST", path:"/tabs/open", query:{profile:"openclaw"}, body:{url:"about:blank"}});
          assert.ok(tab.targetId);
          const snapshot = call("browser.request", {target:"host", method:"GET", path:"/snapshot", query:{profile:"openclaw",targetId:tab.targetId,format:"ai"}});
          assert.equal(typeof snapshot.snapshot, "string");
          assert.equal(call("browser.request", {target:"host", method:"POST", path:"/stop", query:{profile:"openclaw"}}).ok, true);
        }
        stop();
      }
      phase = "missing native capability SecretRef";
      config = structuredClone(configuredBase);
      config.plugins.entries["openclaw-connections"].config = {apiKey:{source:"env",provider:"default",id:"COMPOSIO_API_KEY"}};
      saveConfig(); start();
      kube("exec", "gateway", "-c", "gateway", "--", "node", "--input-type=module", "-e", `
        import assert from 'node:assert/strict';
        import { GatewayClient } from 'openclaw/plugin-sdk/gateway-runtime';
        let admitted, rejected;
        const ready = new Promise((yes,no) => {admitted=yes; rejected=no});
        const client = new GatewayClient({url:'ws://127.0.0.1:18789',token:'${token}',clientName:'cli',mode:'cli',
          role:'operator',scopes:['operator.admin'],deviceIdentity:null,env:process.env,onHelloOk:admitted,onConnectError:rejected});
        try {
          client.start();
          await Promise.race([ready,new Promise((_,reject)=>setTimeout(()=>reject(new Error('Handshake timed out')),10000))]);
          for (const method of ['connections.status','connections.list']) {
            await assert.rejects(client.request(method,{}), error => {
              assert.equal(error.details?.code,'SECRET_SURFACE_UNAVAILABLE');
              assert.match(error.message,/capability:.*apiKey.*unavailable/);
              assert.doesNotMatch(error.message,/synthetic-never-sent/);
              return true;
            });
          }
        } finally {client.stop()}
      `);
      uiAvailable();
      noTools(); stop();
      pod.spec.containers[0].env.push({name:"COMPOSIO_API_KEY",value:"synthetic-never-sent-project-key"});
      for (const preset of release.presets) {
        config = await selectedConfig(preset);
        if (config.plugins.entries["openclaw-connections"]?.enabled !== true) continue;
        config.plugins.entries["openclaw-connections"].config = {apiKey:{source:"env",provider:"default",id:"COMPOSIO_API_KEY"}};
        phase = "configured selected preset " + preset.name;
        saveConfig(); start();
        assert.equal(call("connections.status").configured, true);
        uiAvailable();
        kube("exec", "gateway", "-c", "gateway", "--", "node", "--input-type=module", "-e", `
          import assert from 'node:assert/strict';
          const response = await fetch('http://127.0.0.1:18789/tools/invoke', {method:'POST',
            headers:{authorization:'Bearer ${token}','content-type':'application/json'},
            body:JSON.stringify({tool:'connections_search',args:{},agentId:'main',idempotencyKey:'configured-preset'})});
          assert.equal(response.status,200); assert.match(await response.text(),/no_usable_connections/);
        `);
        stop();
      }
      config = structuredClone(configuredBase);
    }
    phase = "start Gateway with native plugin configuration";
    if (previousImage) pod.spec.containers[0].image = previousTag;
    saveConfig(); start();
    phase = "inspect native plugin";
    const inspected = native("plugins", "inspect", "openclaw-connections", "--runtime", "--json");
    for (const tool of ["connections_search", "connections_describe", "connections_call"]) assert.ok(inspected.includes(tool));
    assert.ok(!inspected.includes("synthetic-never-sent-project-key"));
    phase = "administrator management and UI catalog";
    const before = call("connections.status");
    assert.equal(before.configured, true); assert.ok(before.userId);
    const connection = call("connections.create", {connectorId: "github", name: "Bundle persistence check", grant: {mode: "selected", agentIds: []}});
    const ui = call("plugins.controlUi.list");
    const asset = ui.plugins.find(p => p.pluginId === "openclaw-connections");
    assert.ok(asset);
    const plugin = plugins.find(p => p.id === "openclaw-connections");
    const manifest = JSON.parse(await readFile(resolve("deploy/bundle/plugins/openclaw-connections/openclaw.plugin.json"), "utf8"));
    phase = "UI asset, read-only authority and unconnected tools";
    kube("exec", "gateway", "-c", "gateway", "--", "node", "--input-type=module", "-e", `
      import assert from 'node:assert/strict';
      import { createHash } from 'node:crypto';
      import { GatewayClient } from 'openclaw/plugin-sdk/gateway-runtime';
      const url = new URL(${JSON.stringify(asset.entryUrl)}, 'http://127.0.0.1:18789');
      assert.equal(url.origin, 'http://127.0.0.1:18789');
      const response = await fetch(url, {headers: {authorization: 'Bearer ${token}'}});
      assert.equal(response.status, 200);
      assert.equal(createHash('sha256').update(Buffer.from(await response.arrayBuffer())).digest('hex'), ${JSON.stringify(plugin.files[manifest.controlUi.entry])});
      let admitted, rejected;
      const ready = new Promise((yes, no) => {admitted = yes; rejected = no});
      const client = new GatewayClient({url: 'ws://127.0.0.1:18789', token: '${token}', clientName: 'cli', mode: 'cli', role: 'operator',
        scopes: ['operator.read'], deviceIdentity: null, env: process.env, onHelloOk: admitted, onConnectError: rejected});
      try {
        client.start();
        await Promise.race([ready, new Promise((_, reject) => setTimeout(() => reject(new Error('Handshake timed out')), 10000))]);
        await assert.rejects(client.request('connections.status', {}), /scope|admin/i);
      } finally {client.stop()}
      const search = await fetch('http://127.0.0.1:18789/tools/invoke', {method: 'POST', headers: {'content-type': 'application/json', authorization: 'Bearer ${token}'},
        body: JSON.stringify({tool: 'connections_search', args: {}, agentId: 'main', idempotencyKey: 'bundle-no-accounts'})});
      const body = await search.text();
      assert.equal(search.status, 200); assert.match(body, /no_usable_connections/);
      assert.ok(!body.includes('synthetic-never-sent-project-key'));
    `);
    phase = "private volume permissions and Pod replacement";
    const permission = kube("exec", "gateway", "-c", "gateway", "--", "node", "-e",
      `const fs=require('node:fs'),s=fs.statSync(${JSON.stringify(stateDirectory)});if((s.mode&511)!==448||s.uid!==1000)process.exit(1);`);
    assert.equal(permission.trim(), "");
    stop(); start();
    assert.equal(call("connections.status").userId, before.userId);
    const restored = call("connections.list").items.find(p => p.id === connection.id);
    assert.ok(restored); assert.equal(restored.name, "Bundle persistence check"); assert.deepEqual(restored.grant, {mode: "selected", agentIds: []});
    if (previousImage) {
      phase = "upgrade retained Connections state to the candidate runtime";
      stop(); pod.spec.containers[0].image = tag; start();
      assert.equal(call("connections.status").userId, before.userId);
      const upgraded = call("connections.list").items.find(p => p.id === connection.id);
      assert.ok(upgraded); assert.equal(upgraded.name, restored.name); assert.deepEqual(upgraded.grant, restored.grant);
      uiAvailable();
    }
    phase = "explicitly disabled plugin";
    config.plugins.entries["openclaw-connections"].enabled = false;
    stop(); saveConfig(); start();
    assert.throws(() => call("connections.status"), /unknown method|not found|not registered/i);
  } catch (error) {
    let logs = "";
    if (created) {
      try {logs = kube("logs", "gateway", "-c", "gateway", "--tail=70");} catch {}
    }
    const detail = `${String(error.message)}\n${logs}`
      .replaceAll(token, "[synthetic token]").replaceAll("synthetic-never-sent-project-key", "[synthetic key]");
    throw new Error(`Synthetic Connections check failed at ${phase}: ${detail}`, {cause: error});
  } finally {
    // Remove only the cluster and local tag created with this random test identity.
    if (created) run("k3d", ["cluster", "delete", cluster]);
    if (tagged) run("docker", ["image", "rm", tag]);
    if (previousTagged) run("docker", ["image", "rm", previousTag]);
    await rm(directory, {recursive: true, force: true});
  }
});
