// Run the selected source's unchanged tests against the caller's exact image ID.
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

const [source, image, state, output] = process.argv.slice(2);
const { prepareRuntimeImageSmoke } = await import(pathToFileURL(resolve(source, "scripts/ci/prepare.mjs")));
const { runtimeImageSmokeTests } = await import(pathToFileURL(resolve(source, "scripts/ci/container-release.mjs")));
const prepared = await prepareRuntimeImageSmoke({ image, statePath: resolve(state) });
try {
  const profile = readFileSync(prepared.env.OCC_TEST_CODEX_SECCOMP_PROFILE);
  writeFileSync(resolve(output, "codex-seccomp.json"), profile);
  const sha256 = createHash("sha256").update(profile).digest("hex");
  writeFileSync(resolve(output, "confinement.json"), JSON.stringify({
    seccompSha256: sha256,
    kubernetesProfile: prepared.env.OCC_TEST_KUBERNETES_CODEX_SECCOMP_PROFILE,
    apparmor: prepared.env.OCC_TEST_CODEX_APPARMOR_PROFILE ?? process.env.OCC_TEST_CODEX_APPARMOR_PROFILE ?? null,
    scope: "Selected source's reviewed additions to this native CI node baseline; customer node policy requires review.",
  }, null, 2) + "\n");
  execFileSync(process.execPath, ["--test", "--test-concurrency=1", "--test-reporter=tap", ...runtimeImageSmokeTests], {
    cwd: source,
    env: { ...process.env, ...prepared.env, OCC_TEST_RUNTIME_IMAGE: image, OCC_TEST_IMAGE_TIMEOUT_MULTIPLIER: "1" },
    stdio: "inherit",
  });
} finally {
  await prepared.cleanup();
}
